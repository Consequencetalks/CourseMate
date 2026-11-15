import json
import re
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from openai import APIError, APITimeoutError
from sqlalchemy import select

from app import db
from app.clients.embedding import embed_texts
from app.clients.llm import stream_reply
from app.models import Conversation, Document, Message
from app.prompts import answer_messages
from app.schemas import ChatDelta, ChatDone, ChatError, Citation, ConversationOut, MessageOut
from app.vector_store import query_chunks

CHAT_LIMIT_SECONDS = 90
SOURCE_LIMIT = 5
HISTORY_MESSAGES = 6
TITLE_LIMIT = 80
NEW_CHAT_TITLE = "New chat"
CITATION_RE = re.compile(r"\[S(\d+)\]")

_guard = threading.Lock()
_active: set[str] = set()


def acquire(conversation_id: str) -> bool:
    with _guard:
        if conversation_id in _active:
            return False
        _active.add(conversation_id)
        return True


def release(conversation_id: str) -> None:
    with _guard:
        _active.discard(conversation_id)


def _remaining(started: float) -> float:
    return CHAT_LIMIT_SECONDS - (time.monotonic() - started)


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error(code: str, message: str) -> str:
    return _event("error", ChatError(code=code, message=message).model_dump())


def _conversation_out(row: Conversation) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        title=row.title,
        document_ids=list(row.document_ids),
        created_at=row.created_at,
    )


def _message_out(row: Message) -> MessageOut:
    raw = row.citations or []
    return MessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        citations=[Citation(**item) for item in raw],
        created_at=row.created_at,
    )


def create_conversation(document_ids: list[str]) -> ConversationOut:
    with db.SessionLocal() as session:
        found = set(session.scalars(select(Document.id).where(Document.id.in_(document_ids))).all())
        if any(document_id not in found for document_id in document_ids):
            raise HTTPException(status_code=404, detail="One or more documents were not found.")
        row = Conversation(id=str(uuid4()), title=NEW_CHAT_TITLE, document_ids=document_ids)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _conversation_out(row)


def list_conversations() -> list[ConversationOut]:
    with db.SessionLocal() as session:
        rows = session.scalars(select(Conversation).order_by(Conversation.created_at.desc())).all()
        return [_conversation_out(row) for row in rows]


def list_messages(conversation_id: str) -> list[MessageOut]:
    with db.SessionLocal() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        rows = session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).all()
        return [_message_out(row) for row in rows]


def require_conversation(conversation_id: str) -> None:
    with db.SessionLocal() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        found = set(
            session.scalars(select(Document.id).where(Document.id.in_(conversation.document_ids))).all()
        )
        if any(document_id not in found for document_id in conversation.document_ids):
            raise HTTPException(
                status_code=409,
                detail="A selected document was deleted. Start a new chat.",
            )


def _load_context(conversation_id: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    with db.SessionLocal() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation not found.")
        previous = session.scalars(
            select(Message.content)
            .where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(1)
        ).first()
        recent = session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_MESSAGES)
        ).all()
        history = [(row.role, row.content) for row in reversed(recent)]
        return previous or "", history, list(conversation.document_ids)


def _citations(answer: str, chunks: list[dict]) -> list[Citation]:
    numbers: list[int] = []
    for match in CITATION_RE.finditer(answer):
        number = int(match.group(1))
        if number < 1 or number > len(chunks):
            raise ValueError(match.group(0))
        if number not in numbers:
            numbers.append(number)
    citations = []
    for number in numbers:
        chunk = chunks[number - 1]
        citations.append(
            Citation(
                source_id=f"S{number}",
                document_id=chunk["document_id"],
                filename=chunk["filename"],
                page=int(chunk["page"]),
                excerpt=chunk["text"],
            )
        )
    return citations


def _save_exchange(conversation_id: str, question: str, answer: str, citations: list[Citation]) -> str:
    with db.SessionLocal() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise RuntimeError("Conversation not found.")
        now = datetime.now(timezone.utc)
        session.add(
            Message(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role="user",
                content=question,
                citations=None,
                created_at=now,
            )
        )
        assistant_id = str(uuid4())
        session.add(
            Message(
                id=assistant_id,
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                citations=[item.model_dump() for item in citations],
                created_at=now + timedelta(milliseconds=1),
            )
        )
        if conversation.title == NEW_CHAT_TITLE:
            conversation.title = question[:TITLE_LIMIT].replace("\n", " ")
        session.commit()
        return assistant_id


def _generate(conversation_id: str, question: str, started: float) -> Iterator[str]:
    if _remaining(started) <= 0:
        yield _error("MODEL_TIMEOUT", "The reply timed out. Try again.")
        return

    previous, history, document_ids = _load_context(conversation_id)
    query = f"{previous}\n{question}" if previous else question
    embedding = embed_texts([query])[0]
    chunks = query_chunks(embedding, document_ids, limit=SOURCE_LIMIT)
    sources = [
        {"source_id": f"S{index}", "text": chunk["text"]}
        for index, chunk in enumerate(chunks, start=1)
    ]

    remaining = _remaining(started)
    if remaining <= 0:
        yield _error("MODEL_TIMEOUT", "The reply timed out. Try again.")
        return

    parts: list[str] = []
    try:
        for piece in stream_reply(answer_messages(question, history, sources), timeout=remaining):
            if _remaining(started) <= 0:
                yield _error("MODEL_TIMEOUT", "The reply timed out. Try again.")
                return
            parts.append(piece)
            yield _event("delta", ChatDelta(text=piece).model_dump())
    except (APITimeoutError, TimeoutError):
        yield _error("MODEL_TIMEOUT", "The reply timed out. Try again.")
        return

    answer = "".join(parts)
    if not answer.strip():
        yield _error("MODEL_ERROR", "The model returned an empty reply.")
        return
    try:
        citations = _citations(answer, chunks)
    except ValueError:
        yield _error("INVALID_CITATION", "The reply cited a source that was not retrieved.")
        return

    message_id = _save_exchange(conversation_id, question, answer, citations)
    yield _event("done", ChatDone(message_id=message_id, citations=citations).model_dump())


def chat_events(conversation_id: str, question: str, started: float) -> Iterator[str]:
    try:
        yield from _generate(conversation_id, question, started)
    except Exception:
        yield _error("MODEL_ERROR", "The model request failed.")

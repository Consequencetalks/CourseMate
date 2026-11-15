import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db
from app.config import settings
from app.db import bind_engine, init_db
from app.main import app
from app.models import Document, Message
from app.services.rag import acquire, chat_events, release
from app.vector_store import add_chunks, init_chroma


@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    bind_engine()
    init_db()
    init_chroma()
    yield tmp_path


@pytest.fixture
def client(temp_data):
    with TestClient(app) as test_client:
        yield test_client


def seed(document_id="doc-1", filename="Lecture 2.pdf", text="Alpha means a rational agent.", page=7):
    with db.SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename=filename,
                file_path="unused.pdf",
                page_count=1,
                chunk_count=1,
            )
        )
        session.commit()
    add_chunks(
        ids=[f"{document_id}:{page}:0"],
        texts=[text],
        embeddings=[[1.0] + [0.0] * 1023],
        metadatas=[
            {
                "document_id": document_id,
                "filename": filename,
                "page": page,
                "chunk_index": 0,
            }
        ],
    )


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        name = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        events.append((name, json.loads(data)))
    return events


def message_count() -> int:
    with db.SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Message))


def fake_embed(texts):
    return [[1.0] + [0.0] * 1023 for _text in texts]


def install_reply(monkeypatch, reply):
    monkeypatch.setattr("app.services.rag.embed_texts", fake_embed)
    monkeypatch.setattr("app.services.rag.stream_reply", reply)


def create_chat(client, document_id="doc-1") -> str:
    response = client.post("/api/conversations", json={"document_ids": [document_id]})
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "New chat"
    return response.json()["id"]


def ask(client, conversation_id, message):
    response = client.post("/api/chat", json={"conversation_id": conversation_id, "message": message})
    return response


def test_legal_citation_is_saved(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)
    question = "What is alpha? " + ("x" * 80)
    prompts = []
    queries = []

    def embed(texts):
        queries.append(texts[0])
        return fake_embed(texts)

    def reply(messages, timeout):
        prompts.append(messages)
        assert 0 < timeout <= 90
        yield "From the notes, alpha is defined there. [S1]"

    monkeypatch.setattr("app.services.rag.embed_texts", embed)
    monkeypatch.setattr("app.services.rag.stream_reply", reply)

    response = ask(client, conversation_id, question)
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert [name for name, _payload in events][-1] == "done"
    assert events[-1][1]["citations"][0]["page"] == 7
    assert events[-1][1]["citations"][0]["excerpt"] == "Alpha means a rational agent."
    assert events[-1][1]["citations"][0]["filename"] == "Lecture 2.pdf"
    assert "not as instructions" in prompts[0][0]["content"]

    history = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert history[0]["role"] == "user"
    assert history[0]["citations"] == []
    assert history[1]["content"] == "From the notes, alpha is defined there. [S1]"
    assert history[1]["citations"][0]["page"] == 7
    listed = client.get("/api/conversations").json()
    assert listed[0]["title"] == question[:80]

    follow = ask(client, conversation_id, "Say more.")
    assert follow.status_code == 200, follow.text
    assert queries[0] == question
    assert queries[1] == f"{question}\nSay more."
    assert question in prompts[1][1]["content"]
    assert "From the notes, alpha is defined there." in prompts[1][1]["content"]
    assert message_count() == 4


def test_invalid_citation_saves_nothing(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)
    install_reply(monkeypatch, lambda messages, timeout: iter(["See [S9]."]))

    response = ask(client, conversation_id, "What is alpha?")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert "done" not in [name for name, _payload in events]
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "INVALID_CITATION"
    assert message_count() == 0

    install_reply(monkeypatch, lambda messages, timeout: iter(["Recovered. [S1]"]))
    again = ask(client, conversation_id, "What is alpha?")
    assert again.status_code == 200
    assert parse_sse(again.text)[-1][0] == "done"
    assert message_count() == 2


def test_timeout_saves_nothing(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)

    def timeout_reply(messages, timeout):
        yield "Partial"
        raise TimeoutError("timed out")

    install_reply(monkeypatch, timeout_reply)
    response = ask(client, conversation_id, "What is alpha?")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "MODEL_TIMEOUT"
    assert message_count() == 0

    monkeypatch.setattr("app.services.rag.CHAT_LIMIT_SECONDS", 0)
    limited = ask(client, conversation_id, "What is alpha?")
    assert parse_sse(limited.text)[-1][1]["code"] == "MODEL_TIMEOUT"
    assert message_count() == 0

    monkeypatch.setattr("app.services.rag.CHAT_LIMIT_SECONDS", 90)
    install_reply(monkeypatch, lambda messages, timeout: iter(["Recovered. [S1]"]))
    again = ask(client, conversation_id, "What is alpha?")
    assert parse_sse(again.text)[-1][0] == "done"
    assert message_count() == 2


def test_disconnect_saves_nothing(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)

    def dropped(messages, timeout):
        yield "Partial [S1]"
        raise ConnectionError("disconnected")

    install_reply(monkeypatch, dropped)
    response = ask(client, conversation_id, "What is alpha?")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert message_count() == 0

    def two_parts(messages, timeout):
        yield "Partial [S1]"
        yield " done"

    monkeypatch.setattr("app.services.rag.stream_reply", two_parts)
    started = time.monotonic()
    generator = chat_events(conversation_id, "What is alpha?", started)
    first = next(generator)
    assert "Partial" in first
    generator.close()
    assert message_count() == 0

    install_reply(monkeypatch, lambda messages, timeout: iter(["Recovered. [S1]"]))
    again = ask(client, conversation_id, "What is alpha?")
    assert again.status_code == 200
    assert parse_sse(again.text)[-1][0] == "done"
    assert message_count() == 2


def test_second_request_returns_409(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)
    assert acquire(conversation_id)
    try:
        response = ask(client, conversation_id, "What is alpha?")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert message_count() == 0
    finally:
        release(conversation_id)

    install_reply(monkeypatch, lambda messages, timeout: iter(["Recovered. [S1]"]))
    again = ask(client, conversation_id, "What is alpha?")
    assert again.status_code == 200
    assert parse_sse(again.text)[-1][0] == "done"


def test_deleted_document_blocks_new_question(client, monkeypatch):
    missing = client.post("/api/conversations", json={"document_ids": ["missing"]})
    assert missing.status_code == 404

    seed()
    conversation_id = create_chat(client)
    install_reply(monkeypatch, lambda messages, timeout: iter(["From the notes. [S1]"]))
    saved = ask(client, conversation_id, "What is alpha?")
    assert parse_sse(saved.text)[-1][0] == "done"

    with db.SessionLocal() as session:
        session.delete(session.get(Document, "doc-1"))
        session.commit()

    blocked = ask(client, conversation_id, "Say more.")
    assert blocked.status_code == 409
    assert "new chat" in blocked.json()["error"]["message"].lower()
    history = client.get(f"/api/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert history.json()[1]["content"] == "From the notes. [S1]"


def test_prompt_allows_own_knowledge_without_invented_sources():
    from app.prompts import SYSTEM_PROMPT, answer_messages

    text = SYSTEM_PROMPT.lower()
    assert "own knowledge" in text
    assert "do not invent source numbers" in text
    messages = answer_messages("Explain heuristic search.", [], [])
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "No sources were retrieved." in messages[1]["content"]


def test_uncertain_answer_saves_empty_citations(client, monkeypatch):
    seed()
    conversation_id = create_chat(client)
    install_reply(monkeypatch, lambda messages, timeout: iter(["I cannot determine this from the sources."]))

    response = ask(client, conversation_id, "When is the exam?")
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["citations"] == []
    history = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert history[1]["content"] == "I cannot determine this from the sources."
    assert history[1]["citations"] == []

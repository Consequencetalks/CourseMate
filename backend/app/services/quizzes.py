import json
import re
import time
from uuid import uuid4

from fastapi import HTTPException
from openai import APITimeoutError
from sqlalchemy import select

from app import db
from app.clients.embedding import embed_texts
from app.clients.llm import complete
from app.models import Document, Quiz, QuizAttempt
from app.prompts import quiz_prompt
from app.schemas import (
    PublicQuestion,
    QuestionResult,
    QuizCreated,
    QuizDetail,
    QuizResult,
    QuizSummary,
)
from app.vector_store import chunks_for_pages, query_chunks

QUIZ_LIMIT_SECONDS = 90
SOURCE_LIMIT = 8
PAGE_LIMIT = 4
MIN_CHARS = 12
CONTEXT_LIMIT = 20
QUESTION_COUNT = 3
OPTIONS = ("A", "B", "C", "D")
SOURCE_ID_RE = re.compile(r"S(\d+)")


class InsufficientContext(Exception):
    pass


class InvalidQuiz(Exception):
    pass


def _insufficient() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "INSUFFICIENT_CONTEXT",
            "message": "Not enough material for this topic. Try another topic.",
        },
    )


def _remaining(started: float) -> float:
    return QUIZ_LIMIT_SECONDS - (time.monotonic() - started)


def _require_documents(document_ids: list[str]) -> None:
    with db.SessionLocal() as session:
        found = set(session.scalars(select(Document.id).where(Document.id.in_(document_ids))).all())
        if any(document_id not in found for document_id in document_ids):
            raise HTTPException(status_code=404, detail="One or more documents were not found.")


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _loads(raw: str) -> dict:
    try:
        payload = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise InvalidQuiz() from exc
    if not isinstance(payload, dict):
        raise InvalidQuiz()
    return payload


def _citations(source_ids: list, chunks: list[dict]) -> list[dict]:
    if not isinstance(source_ids, list) or not source_ids:
        raise InvalidQuiz()
    citations = []
    seen: list[int] = []
    for source_id in source_ids:
        if not isinstance(source_id, str):
            raise InvalidQuiz()
        match = SOURCE_ID_RE.fullmatch(source_id)
        if match is None:
            raise InvalidQuiz()
        number = int(match.group(1))
        if number in seen:
            continue
        if number < 1 or number > len(chunks):
            raise InvalidQuiz()
        seen.append(number)
        chunk = chunks[number - 1]
        citations.append(
            {
                "source_id": f"S{number}",
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "page": int(chunk["page"]),
                "excerpt": chunk["text"],
            }
        )
    if not citations:
        raise InvalidQuiz()
    return citations


def _validate(payload: dict, chunks: list[dict]) -> list[dict]:
    if payload.get("insufficient") is True:
        raise InsufficientContext()
    questions = payload.get("questions")
    if not isinstance(questions, list) or len(questions) != QUESTION_COUNT:
        raise InvalidQuiz()
    saved = []
    for item in questions:
        if not isinstance(item, dict):
            raise InvalidQuiz()
        stem = item.get("stem")
        options = item.get("options")
        correct = item.get("correct_option")
        explanation = item.get("explanation")
        if not isinstance(stem, str) or not stem.strip():
            raise InvalidQuiz()
        if not isinstance(options, dict) or not isinstance(explanation, str) or not explanation.strip():
            raise InvalidQuiz()
        if correct not in OPTIONS:
            raise InvalidQuiz()
        cleaned = {}
        for key in OPTIONS:
            value = options.get(key)
            if not isinstance(value, str) or not value.strip():
                raise InvalidQuiz()
            cleaned[key] = value.strip()
        saved.append(
            {
                "id": str(uuid4()),
                "stem": stem.strip(),
                "options": cleaned,
                "correct_option": correct,
                "explanation": explanation.strip(),
                "citations": _citations(item.get("source_ids"), chunks),
            }
        )
    return saved


def _generate_once(prompt: str, chunks: list[dict], started: float) -> list[dict]:
    remaining = _remaining(started)
    if remaining <= 0:
        raise HTTPException(status_code=504, detail="The quiz timed out. Try again.")
    try:
        raw = complete(prompt, max_tokens=2048, timeout=remaining)
    except (APITimeoutError, TimeoutError) as exc:
        raise HTTPException(status_code=504, detail="The quiz timed out. Try again.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The quiz could not be generated.") from exc
    return _validate(_loads(raw), chunks)


def _public(question: dict) -> PublicQuestion:
    return PublicQuestion(id=question["id"], stem=question["stem"], options=question["options"])


def _quiz_chunks(document_ids: list[str], topic: str) -> list[dict]:
    seeds = query_chunks(embed_texts([topic])[0], document_ids, limit=SOURCE_LIMIT)
    pages: list[tuple[str, int]] = []
    for chunk in seeds:
        pair = (chunk["document_id"], int(chunk["page"]))
        if pair not in pages:
            pages.append(pair)
        if len(pages) == PAGE_LIMIT:
            break
    readable = [chunk for chunk in chunks_for_pages(pages) if len(chunk["text"].strip()) >= MIN_CHARS]
    if len(readable) > CONTEXT_LIMIT:
        readable = sorted(readable, key=lambda chunk: len(chunk["text"].strip()), reverse=True)[:CONTEXT_LIMIT]
    readable.sort(key=lambda chunk: (chunk["page"], chunk["chunk_index"]))
    return readable


def create_quiz(document_ids: list[str], topic: str, language: str) -> QuizCreated:
    started = time.monotonic()
    _require_documents(document_ids)
    chunks = _quiz_chunks(document_ids, topic)
    if not chunks:
        raise _insufficient()
    sources = [
        {"source_id": f"S{index}", "text": chunk["text"]}
        for index, chunk in enumerate(chunks, start=1)
    ]
    prompt = quiz_prompt(topic, language, sources)
    try:
        questions = _generate_once(prompt, chunks, started)
    except InsufficientContext:
        raise _insufficient() from None
    except InvalidQuiz:
        try:
            questions = _generate_once(prompt, chunks, started)
        except InsufficientContext:
            raise _insufficient() from None
        except InvalidQuiz:
            raise HTTPException(status_code=502, detail="The quiz could not be generated.") from None
    quiz_id = str(uuid4())
    with db.SessionLocal() as session:
        session.add(
            Quiz(
                id=quiz_id,
                document_ids=document_ids,
                topic=topic,
                language=language,
                questions=questions,
            )
        )
        session.commit()
    return QuizCreated(id=quiz_id, questions=[_public(question) for question in questions])


def list_quizzes() -> list[QuizSummary]:
    with db.SessionLocal() as session:
        rows = session.scalars(select(Quiz).order_by(Quiz.created_at.desc())).all()
        submitted = set(session.scalars(select(QuizAttempt.quiz_id)).all())
        return [
            QuizSummary(
                id=row.id,
                topic=row.topic,
                language=row.language,
                created_at=row.created_at,
                submitted=row.id in submitted,
            )
            for row in rows
        ]


def _load(quiz_id: str) -> tuple[dict, list[dict] | None]:
    with db.SessionLocal() as session:
        quiz = session.get(Quiz, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        attempt = session.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_id))
        info = {
            "id": quiz.id,
            "topic": quiz.topic,
            "language": quiz.language,
            "created_at": quiz.created_at,
            "questions": list(quiz.questions),
        }
        answers = list(attempt.answers) if attempt is not None else None
        return info, answers


def _score(questions: list[dict], answers: dict[str, str]) -> QuizResult:
    results = []
    correct_count = 0
    for question in questions:
        selected = answers[question["id"]]
        correct = selected == question["correct_option"]
        correct_count += int(correct)
        results.append(
            QuestionResult(
                id=question["id"],
                stem=question["stem"],
                options=question["options"],
                selected_option=selected,
                correct_option=question["correct_option"],
                correct=correct,
                explanation=question["explanation"],
                citations=question["citations"],
            )
        )
    return QuizResult(correct_count=correct_count, total=len(questions), questions=results)


def _result(questions: list[dict], answers: list[dict]) -> QuizResult:
    chosen = {item["question_id"]: item["option"] for item in answers}
    return _score(questions, chosen)


def get_quiz(quiz_id: str) -> QuizDetail:
    quiz, answers = _load(quiz_id)
    return QuizDetail(
        id=quiz["id"],
        topic=quiz["topic"],
        language=quiz["language"],
        created_at=quiz["created_at"],
        questions=[_public(question) for question in quiz["questions"]],
        result=_result(quiz["questions"], answers) if answers is not None else None,
    )


def saved_result(quiz_id: str) -> QuizResult | None:
    quiz, answers = _load(quiz_id)
    if answers is None:
        return None
    return _result(quiz["questions"], answers)


def score_quiz(quiz_id: str, answers: list) -> QuizResult:
    quiz, existing = _load(quiz_id)
    if existing is not None:
        return _result(quiz["questions"], existing)
    expected = [question["id"] for question in quiz["questions"]]
    got = [answer.question_id for answer in answers]
    if len(got) != len(expected) or set(got) != set(expected) or len(set(got)) != len(got):
        raise HTTPException(status_code=422, detail="Submit one answer for every question.")
    chosen = {answer.question_id: answer.option for answer in answers}
    result = _score(quiz["questions"], chosen)
    with db.SessionLocal() as session:
        session.add(
            QuizAttempt(
                id=str(uuid4()),
                quiz_id=quiz_id,
                answers=[{"question_id": answer.question_id, "option": answer.option} for answer in answers],
                correct_count=result.correct_count,
                total=result.total,
            )
        )
        session.commit()
    return result

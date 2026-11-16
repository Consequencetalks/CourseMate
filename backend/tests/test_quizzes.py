import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db
from app.config import settings
from app.db import bind_engine, init_db
from app.main import app
from app.models import Document, Quiz, QuizAttempt
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


def seed():
    with db.SessionLocal() as session:
        session.add(
            Document(
                id="doc-1",
                filename="Lecture 2.pdf",
                file_path="unused.pdf",
                page_count=1,
                chunk_count=1,
            )
        )
        session.commit()
    add_chunks(
        ids=["doc-1:7:0"],
        texts=["Alpha means a rational agent."],
        embeddings=[[1.0] + [0.0] * 1023],
        metadatas=[{"document_id": "doc-1", "filename": "Lecture 2.pdf", "page": 7, "chunk_index": 0}],
    )


def question(index: int) -> dict:
    return {
        "stem": f"Question {index}",
        "options": {"A": "alpha", "B": "beta", "C": "gamma", "D": "delta"},
        "correct_option": "A",
        "explanation": f"Because the source says so for question {index}.",
        "source_ids": ["S1"],
    }


def valid_payload() -> dict:
    return {"questions": [question(1), question(2), question(3)]}


def install_model(monkeypatch, replies: list[str]):
    pending = list(replies)

    def complete(prompt, max_tokens=1024, timeout=60):
        assert timeout > 0
        assert max_tokens == 2048
        return pending.pop(0)

    monkeypatch.setattr("app.services.quizzes.embed_texts", lambda texts: [[1.0] + [0.0] * 1023])
    monkeypatch.setattr("app.services.quizzes.complete", complete)
    return pending


def quiz_count() -> int:
    with db.SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Quiz))


def attempt_count() -> int:
    with db.SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(QuizAttempt))


def insert_quiz(correct: tuple[str, str, str] = ("A", "B", "C")) -> tuple[str, list[str]]:
    questions = []
    for index, answer in enumerate(correct):
        item = question(index)
        item["id"] = str(uuid4())
        item["correct_option"] = answer
        item["citations"] = [
            {
                "source_id": "S1",
                "document_id": "doc-1",
                "filename": "Lecture 2.pdf",
                "page": 7,
                "excerpt": "Alpha means a rational agent.",
            }
        ]
        questions.append(item)
    quiz_id = str(uuid4())
    with db.SessionLocal() as session:
        session.add(
            Quiz(
                id=quiz_id,
                document_ids=["doc-1"],
                topic="Alpha",
                language="en",
                questions=questions,
            )
        )
        session.commit()
    return quiz_id, [item["id"] for item in questions]


def answers_for(ids: list[str], options: list[str]) -> dict:
    return {"answers": [{"question_id": ids[index], "option": options[index]} for index in range(len(ids))]}


def test_legal_quiz_hides_answers(client, monkeypatch):
    seed()
    missing = client.post("/api/quizzes", json={"document_ids": ["missing"], "topic": "Alpha", "language": "en"})
    assert missing.status_code == 404

    install_model(monkeypatch, ["```json\n" + json.dumps(valid_payload()) + "\n```"])
    response = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Alpha", "language": "en"},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created["questions"][0]) == {"id", "stem", "options"}
    detail = client.get(f"/api/quizzes/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["result"] is None
    assert detail.json()["document_ids"] == ["doc-1"]
    assert set(detail.json()["questions"][0]) == {"id", "stem", "options"}
    with db.SessionLocal() as session:
        stored = session.get(Quiz, created["id"])
        citation = stored.questions[0]["citations"][0]
    assert citation["page"] == 7
    assert citation["excerpt"] == "Alpha means a rational agent."
    assert citation["filename"] == "Lecture 2.pdf"


def test_scores_all_partial_and_none(client):
    cases = [
        (["A", "B", "C"], 3),
        (["A", "D", "D"], 1),
        (["D", "D", "D"], 0),
    ]
    for options, expected in cases:
        quiz_id, ids = insert_quiz()
        response = client.post(f"/api/quizzes/{quiz_id}/submit", json=answers_for(ids, options))
        assert response.status_code == 200, response.text
        assert response.json()["correct_count"] == expected
        assert response.json()["total"] == 3
        assert response.json()["questions"][0]["explanation"]


def test_rejects_incomplete_duplicate_and_illegal_answers(client):
    quiz_id, ids = insert_quiz()
    missing = client.post(
        f"/api/quizzes/{quiz_id}/submit",
        json=answers_for(ids[:2], ["A", "B"]),
    )
    assert missing.status_code == 422
    duplicate = client.post(
        f"/api/quizzes/{quiz_id}/submit",
        json={
            "answers": [
                {"question_id": ids[0], "option": "A"},
                {"question_id": ids[0], "option": "B"},
                {"question_id": ids[1], "option": "B"},
            ]
        },
    )
    assert duplicate.status_code == 422
    illegal = client.post(
        f"/api/quizzes/{quiz_id}/submit",
        json={"answers": [{"question_id": ids[0], "option": "E"}]},
    )
    assert illegal.status_code == 422
    assert attempt_count() == 0


def test_repeat_submit_keeps_the_first_score(client):
    quiz_id, ids = insert_quiz()
    first = client.post(f"/api/quizzes/{quiz_id}/submit", json=answers_for(ids, ["A", "B", "C"]))
    assert first.json()["correct_count"] == 3
    second = client.post(f"/api/quizzes/{quiz_id}/submit", json=answers_for(ids, ["D", "D", "D"]))
    assert second.status_code == 200
    assert second.json()["correct_count"] == 3
    assert attempt_count() == 1
    detail = client.get(f"/api/quizzes/{quiz_id}")
    assert detail.json()["result"]["correct_count"] == 3


def test_insufficient_context_does_not_retry(client, monkeypatch):
    seed()
    calls = install_model(monkeypatch, ['{"insufficient": true}'])
    response = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Alpha", "language": "en"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_CONTEXT"
    assert calls == []
    assert quiz_count() == 0


def test_invalid_json_retries_once(client, monkeypatch):
    seed()
    calls = install_model(monkeypatch, ["not json", json.dumps(valid_payload())])
    response = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Alpha", "language": "en"},
    )
    assert response.status_code == 201, response.text
    assert calls == []

    calls = install_model(monkeypatch, ["not json", "still not json"])
    failed = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Alpha", "language": "en"},
    )
    assert failed.status_code == 502
    assert calls == []
    assert quiz_count() == 1


def add_document() -> None:
    with db.SessionLocal() as session:
        session.add(
            Document(
                id="doc-1",
                filename="Lecture 2.pdf",
                file_path="unused.pdf",
                page_count=1,
                chunk_count=1,
            )
        )
        session.commit()


def test_page_body_is_sent_with_the_nearest_titles(client, monkeypatch):
    add_document()
    ids = []
    texts = []
    embeddings = []
    metadatas = []
    for page in range(1, 9):
        vector = [0.0] * 1024
        vector[0] = 1.0
        vector[1] = page / 100
        ids.append(f"doc-1:{page}:0")
        texts.append(f"Heading page {page:02d}")
        embeddings.append(vector)
        metadatas.append({"document_id": "doc-1", "filename": "Lecture 2.pdf", "page": page, "chunk_index": 0})
    body = [0.0] * 1024
    body[2] = 1.0
    ids.append("doc-1:1:1")
    texts.append("The evaluation function is f(n) = g(n) + h(n) for the selected node.")
    embeddings.append(body)
    metadatas.append({"document_id": "doc-1", "filename": "Lecture 2.pdf", "page": 1, "chunk_index": 1})
    add_chunks(ids=ids, texts=texts, embeddings=embeddings, metadatas=metadatas)

    prompts = []

    def complete(prompt, max_tokens=1024, timeout=60):
        prompts.append(prompt)
        return json.dumps(valid_payload())

    monkeypatch.setattr("app.services.quizzes.embed_texts", lambda texts: [[1.0] + [0.0] * 1023])
    monkeypatch.setattr("app.services.quizzes.complete", complete)
    response = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Heuristic Search", "language": "en"},
    )
    assert response.status_code == 201, response.text
    assert "f(n) = g(n) + h(n)" in prompts[0]
    assert "Heading page 05" not in prompts[0]


def test_short_labels_do_not_call_the_model(client, monkeypatch):
    add_document()
    add_chunks(
        ids=["doc-1:1:0", "doc-1:2:0"],
        texts=["ABCD", "WXYZ"],
        embeddings=[[1.0] + [0.0] * 1023, [1.0] + [0.0] * 1023],
        metadatas=[
            {"document_id": "doc-1", "filename": "Lecture 2.pdf", "page": 1, "chunk_index": 0},
            {"document_id": "doc-1", "filename": "Lecture 2.pdf", "page": 2, "chunk_index": 0},
        ],
    )

    def complete(prompt, max_tokens=1024, timeout=60):
        raise AssertionError("model should not be called")

    monkeypatch.setattr("app.services.quizzes.embed_texts", lambda texts: [[1.0] + [0.0] * 1023])
    monkeypatch.setattr("app.services.quizzes.complete", complete)
    response = client.post(
        "/api/quizzes",
        json={"document_ids": ["doc-1"], "topic": "Heuristic Search", "language": "en"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_CONTEXT"
    assert quiz_count() == 0

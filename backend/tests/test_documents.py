from pathlib import Path

import pymupdf
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import db
from app.config import settings
from app.db import bind_engine, init_db
from app.models import Document
from app.services.documents import build_chunks, extract_paragraphs, import_pdf, split_text
from app.vector_store import init_chroma, query_chunks


def test_short_paragraph_stays_whole():
    assert split_text("Short paragraph.") == ["Short paragraph."]
    chunks = build_chunks([(1, "One."), (1, "Two."), (2, "Page two.")])
    assert [(chunk.page, chunk.index, chunk.text) for chunk in chunks] == [
        (1, 0, "One."),
        (1, 1, "Two."),
        (2, 0, "Page two."),
    ]


def test_long_paragraph_overlaps_without_crossing_pages():
    paragraph = " ".join(f"word{i}" for i in range(250))
    assert len(paragraph) > 800
    chunks = build_chunks([(1, paragraph), (2, "Only on page two.")])
    page_one = [chunk.text for chunk in chunks if chunk.page == 1]
    page_two = [chunk for chunk in chunks if chunk.page == 2]
    assert len(page_one) >= 2
    assert all(len(text) <= 800 for text in page_one)
    assert page_one[0][-60:] in page_one[1]
    assert len(page_two) == 1
    assert page_two[0].text == "Only on page two."
    assert page_two[0].index == 0


@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    bind_engine()
    init_db()
    init_chroma()
    yield tmp_path


def pdf_bytes(pages: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for index, _text in enumerate(texts):
        vector = [0.0] * 1024
        vector[index % 1024] = 1.0
        vectors.append(vector)
    return vectors


def test_filtered_query_does_not_cross_documents(temp_data):
    from app.vector_store import add_chunks

    add_chunks(
        ids=["a:1:0"],
        texts=["alpha only"],
        embeddings=[[1.0] + [0.0] * 1023],
        metadatas=[{"document_id": "a", "filename": "a.pdf", "page": 1, "chunk_index": 0}],
    )
    add_chunks(
        ids=["b:1:0"],
        texts=["beta only"],
        embeddings=[[0.0, 1.0] + [0.0] * 1022],
        metadatas=[{"document_id": "b", "filename": "b.pdf", "page": 3, "chunk_index": 0}],
    )
    rows = query_chunks([1.0] + [0.0] * 1023, ["b"])
    assert [row["text"] for row in rows] == ["beta only"]
    assert rows[0]["page"] == 3
    assert rows[0]["document_id"] == "b"


def test_embed_failure_leaves_no_partial_document_and_retry_works(temp_data, monkeypatch):
    content = pdf_bytes(["Hello from the only page."])

    def fail(_texts):
        raise RuntimeError("API down")

    monkeypatch.setattr("app.services.documents.embed_texts", fail)
    with pytest.raises(HTTPException) as exc:
        import_pdf(content, "notes.pdf")
    assert exc.value.status_code == 502
    assert list(Path(temp_data / "uploads").glob("*.pdf")) == []
    with db.SessionLocal() as session:
        assert session.scalars(select(Document)).all() == []

    monkeypatch.setattr("app.services.documents.embed_texts", fake_embed)
    created = import_pdf(content, "notes.pdf")
    assert created.chunk_count == 1
    assert created.page_count == 1
    assert (temp_data / "uploads" / f"{created.id}.pdf").is_file()
    rows = query_chunks(fake_embed(["hello"])[0], [created.id])
    assert rows[0]["text"] == "Hello from the only page."
    assert rows[0]["page"] == 1


def test_blank_page_is_reported_and_keeps_real_page_number(temp_data, monkeypatch):
    monkeypatch.setattr("app.services.documents.embed_texts", fake_embed)
    created = import_pdf(pdf_bytes(["Visible text", ""]), "mixed.pdf")
    assert created.page_count == 2
    assert created.warnings == ["Skipped pages with no extractable text: 2."]
    rows = query_chunks(fake_embed(["visible"])[0], [created.id])
    assert rows[0]["page"] == 1


def test_rejects_invalid_files(temp_data, monkeypatch):
    monkeypatch.setattr("app.services.documents.embed_texts", fake_embed)
    with pytest.raises(HTTPException) as not_pdf:
        import_pdf(b"hello", "notes.txt")
    assert not_pdf.value.status_code == 422

    with pytest.raises(HTTPException) as broken:
        import_pdf(b"%PDF-1.4 not a real pdf", "broken.pdf")
    assert broken.value.status_code == 422

    with pytest.raises(HTTPException) as blank:
        import_pdf(pdf_bytes([""]), "scan.pdf")
    assert blank.value.status_code == 422
    assert "no extractable text" in blank.value.detail

    with pytest.raises(HTTPException) as huge:
        extract_paragraphs(b"%PDF" + b"x" * (20 * 1024 * 1024))
    assert huge.value.status_code == 413

    too_many = pymupdf.open()
    for _ in range(101):
        too_many.new_page()
    content = too_many.tobytes()
    too_many.close()
    with pytest.raises(HTTPException) as pages:
        import_pdf(content, "long.pdf")
    assert pages.value.status_code == 422
    assert list(Path(temp_data / "uploads").glob("*.pdf")) == []


def test_import_timeout_cleans_up(temp_data, monkeypatch):
    monkeypatch.setattr("app.services.documents.IMPORT_TIMEOUT_SECONDS", -1)
    called = False

    def fail_if_called(_texts):
        nonlocal called
        called = True
        return fake_embed(_texts)

    monkeypatch.setattr("app.services.documents.embed_texts", fail_if_called)
    with pytest.raises(HTTPException) as exc:
        import_pdf(pdf_bytes(["Timeout me."]), "slow.pdf")
    assert exc.value.status_code == 504
    assert called is False
    assert list(Path(temp_data / "uploads").glob("*.pdf")) == []

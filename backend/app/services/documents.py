import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pymupdf
from fastapi import HTTPException
from sqlalchemy import select

from app import db
from app.clients.embedding import embed_texts
from app.config import settings
from app.models import Document
from app.schemas import DocumentCreated, DocumentOut
from app.vector_store import add_chunks, delete_document_vectors

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBED_BATCH = 10
IMPORT_TIMEOUT_SECONDS = 180


@dataclass
class Chunk:
    page: int
    index: int
    text: str


def split_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind(" "), window.rfind("\n"))
            if cut > 0:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        next_start = end - CHUNK_OVERLAP
        if next_start <= start:
            next_start = end
        start = next_start
    return pieces


def build_chunks(paragraphs: list[tuple[int, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    page_indexes: dict[int, int] = {}
    for page, text in paragraphs:
        for piece in split_text(text):
            index = page_indexes.get(page, 0)
            chunks.append(Chunk(page=page, index=index, text=piece))
            page_indexes[page] = index + 1
    return chunks


def extract_paragraphs(content: bytes) -> tuple[list[tuple[int, str]], list[str], int]:
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 20 MB.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Only PDF files can be imported.")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=422, detail="This PDF could not be opened.") from exc
    with document:
        return _read_document(document)


def _read_document(document) -> tuple[list[tuple[int, str]], list[str], int]:
    if document.page_count > MAX_PAGES:
        raise HTTPException(status_code=422, detail="This PDF has more than 100 pages.")
    paragraphs: list[tuple[int, str]] = []
    skipped: list[int] = []
    for index, page in enumerate(document, start=1):
        texts = []
        blocks = page.get_text("blocks")
        for block in sorted(blocks, key=lambda item: (item[1], item[0])):
            if len(block) >= 7 and block[6] != 0:
                continue
            text = str(block[4]).strip()
            if text:
                texts.append(text)
        if texts:
            paragraphs.extend((index, text) for text in texts)
        else:
            skipped.append(index)
    warnings = []
    if skipped:
        numbers = ", ".join(str(number) for number in skipped)
        warnings.append(f"Skipped pages with no extractable text: {numbers}.")
    return paragraphs, warnings, document.page_count


def _cleanup(document_id: str, path: Path) -> None:
    try:
        delete_document_vectors(document_id)
    finally:
        path.unlink(missing_ok=True)


def import_pdf(content: bytes, filename: str) -> DocumentCreated:
    paragraphs, warnings, page_count = extract_paragraphs(content)
    chunks = build_chunks(paragraphs)
    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="This PDF has no extractable text. Scanned PDFs are not supported.",
        )
    document_id = str(uuid4())
    safe_name = Path(filename).name or "document.pdf"
    if len(safe_name) > 255:
        safe_name = safe_name[-255:]
    path = settings.data_path / "uploads" / f"{document_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    started = time.monotonic()
    try:
        for offset in range(0, len(chunks), EMBED_BATCH):
            if time.monotonic() - started > IMPORT_TIMEOUT_SECONDS:
                raise HTTPException(
                    status_code=504,
                    detail="Import timed out. Split the file and try again.",
                )
            batch = chunks[offset : offset + EMBED_BATCH]
            try:
                vectors = embed_texts([chunk.text for chunk in batch])
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}") from exc
            add_chunks(
                ids=[f"{document_id}:{chunk.page}:{chunk.index}" for chunk in batch],
                texts=[chunk.text for chunk in batch],
                embeddings=vectors,
                metadatas=[
                    {
                        "document_id": document_id,
                        "filename": safe_name,
                        "page": chunk.page,
                        "chunk_index": chunk.index,
                    }
                    for chunk in batch
                ],
            )
        with db.SessionLocal() as session:
            row = Document(
                id=document_id,
                filename=safe_name,
                file_path=str(path),
                page_count=page_count,
                chunk_count=len(chunks),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return DocumentCreated(
                id=row.id,
                filename=row.filename,
                page_count=row.page_count,
                chunk_count=row.chunk_count,
                created_at=row.created_at,
                warnings=warnings,
            )
    except Exception:
        _cleanup(document_id, path)
        raise


def list_documents() -> list[DocumentOut]:
    with db.SessionLocal() as session:
        rows = session.scalars(select(Document).order_by(Document.created_at.desc())).all()
        return [
            DocumentOut(
                id=row.id,
                filename=row.filename,
                page_count=row.page_count,
                chunk_count=row.chunk_count,
                created_at=row.created_at,
            )
            for row in rows
        ]


def get_document_file(document_id: str) -> tuple[Path, str]:
    with db.SessionLocal() as session:
        row = session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        path = Path(row.file_path)
        filename = row.filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found.")
    return path, filename


def delete_document(document_id: str) -> None:
    with db.SessionLocal() as session:
        row = session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        path = Path(row.file_path)
        delete_document_vectors(document_id)
        path.unlink(missing_ok=True)
        session.delete(row)
        session.commit()

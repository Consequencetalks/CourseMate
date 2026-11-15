from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.schemas import DocumentCreated, DocumentOut
from app.services.documents import delete_document, get_document_file, import_pdf, list_documents

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", status_code=201, response_model=DocumentCreated)
async def create_document(file: UploadFile = File(...)) -> DocumentCreated:
    content = await file.read()
    return await run_in_threadpool(import_pdf, content, file.filename or "document.pdf")


@router.get("", response_model=list[DocumentOut])
def get_documents() -> list[DocumentOut]:
    return list_documents()


@router.get("/{document_id}/file")
def read_document_file(document_id: str) -> FileResponse:
    path, filename = get_document_file(document_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=204)
def remove_document(document_id: str) -> Response:
    delete_document(document_id)
    return Response(status_code=204)

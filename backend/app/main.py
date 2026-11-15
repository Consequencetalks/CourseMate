from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import init_db
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router
from app.routers.documents import router as documents_router
from app.routers.quizzes import router as quizzes_router
from app.schemas import ErrorResponse, HealthResponse
from app.vector_store import init_chroma

ERROR_CODES = {
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    422: "INVALID",
    502: "MODEL_ERROR",
    504: "MODEL_TIMEOUT",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    init_chroma()
    yield


app = FastAPI(title="CourseMate", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(quizzes_router)


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
    else:
        code = ERROR_CODES.get(exc.status_code, "ERROR")
        message = str(detail)
    body = ErrorResponse(error={"code": code, "message": message})
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
    body = ErrorResponse(error={"code": "INVALID", "message": message or "Invalid request"})
    return JSONResponse(status_code=422, content=body.model_dump())


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")

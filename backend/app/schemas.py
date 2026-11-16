from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class DocumentOut(BaseModel):
    id: str
    filename: str
    page_count: int
    chunk_count: int
    created_at: datetime


class DocumentCreated(DocumentOut):
    warnings: list[str]


class ConversationCreate(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=5)


class ConversationOut(BaseModel):
    id: str
    title: str
    document_ids: list[str]
    created_at: datetime


class Citation(BaseModel):
    source_id: str
    document_id: str
    filename: str
    page: int
    excerpt: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[Citation]
    created_at: datetime


class ChatRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=2000)


class ChatDelta(BaseModel):
    text: str


class ChatDone(BaseModel):
    message_id: str
    citations: list[Citation]


class ChatError(BaseModel):
    code: str
    message: str


class QuizCreate(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=5)
    topic: str = Field(min_length=1, max_length=200)
    language: Literal["zh", "en"]


class PublicQuestion(BaseModel):
    id: str
    stem: str
    options: dict[str, str]


class QuizCreated(BaseModel):
    id: str
    questions: list[PublicQuestion]


class QuizSummary(BaseModel):
    id: str
    topic: str
    language: str
    created_at: datetime
    submitted: bool


class AnswerIn(BaseModel):
    question_id: str
    option: Literal["A", "B", "C", "D"]


class QuizSubmit(BaseModel):
    answers: list[AnswerIn]


class QuestionResult(PublicQuestion):
    selected_option: str
    correct_option: str
    correct: bool
    explanation: str
    citations: list[Citation]


class QuizResult(BaseModel):
    correct_count: int
    total: int
    questions: list[QuestionResult]


class QuizDetail(BaseModel):
    id: str
    topic: str
    language: str
    created_at: datetime
    questions: list[PublicQuestion]
    result: QuizResult | None = None


class SpeechText(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

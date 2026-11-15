from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.schemas import QuizCreate, QuizCreated, QuizDetail, QuizResult, QuizSubmit, QuizSummary
from app.services.quizzes import create_quiz, get_quiz, list_quizzes, saved_result, score_quiz

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.post("", status_code=201, response_model=QuizCreated)
def post_quiz(body: QuizCreate) -> QuizCreated:
    return create_quiz(body.document_ids, body.topic, body.language)


@router.get("", response_model=list[QuizSummary])
def get_quizzes() -> list[QuizSummary]:
    return list_quizzes()


@router.get("/{quiz_id}", response_model=QuizDetail)
def read_quiz(quiz_id: str) -> QuizDetail:
    return get_quiz(quiz_id)


@router.post("/{quiz_id}/submit", response_model=QuizResult)
async def submit_quiz(quiz_id: str, request: Request) -> QuizResult:
    saved = saved_result(quiz_id)
    if saved is not None:
        return saved
    try:
        body = QuizSubmit.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Submit one answer for every question.") from exc
    return score_quiz(quiz_id, body.answers)

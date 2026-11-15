from fastapi import APIRouter

from app.schemas import ConversationCreate, ConversationOut, MessageOut
from app.services.rag import create_conversation, list_conversations, list_messages

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", status_code=201, response_model=ConversationOut)
def post_conversation(body: ConversationCreate) -> ConversationOut:
    return create_conversation(body.document_ids)


@router.get("", response_model=list[ConversationOut])
def get_conversations() -> list[ConversationOut]:
    return list_conversations()


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: str) -> list[MessageOut]:
    return list_messages(conversation_id)

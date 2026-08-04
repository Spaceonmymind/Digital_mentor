import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/messages", response_model=ChatMessageResponse)
async def create_chat_message(payload: ChatMessageRequest, session: AsyncSession = Depends(get_session)) -> ChatMessageResponse:
    message = await ChatService().answer(session, payload.analysis_id, payload.message)
    logger.info("chat_message_created analysis_id=%s message_id=%s", payload.analysis_id, message.id)
    return ChatMessageResponse(message_id=message.id, answer=message.content)

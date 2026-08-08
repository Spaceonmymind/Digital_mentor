from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    analysis_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    message_id: str
    answer: str

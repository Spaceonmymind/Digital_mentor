from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    status: str
    created_at: datetime


class DocumentContentResponse(BaseModel):
    document_id: str
    content: dict

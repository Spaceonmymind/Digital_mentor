from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    status: str
    extraction_status: str | None = None
    created_at: datetime


class DocumentContentResponse(BaseModel):
    document_id: str
    content: dict

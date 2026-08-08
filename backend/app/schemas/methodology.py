from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MethodologyReference(BaseModel):
    methodology_id: str
    methodology_version: str


class AgentTraceItem(BaseModel):
    agent_code: str
    agent_version: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_reference: str | None = None
    error_code: str | None = None


class AnalysisEvidence(BaseModel):
    document_id: str
    page: int | None = None
    section: str | None = None
    quote: str | None = None
    block_index: int | None = None
    extra: dict[str, Any] = {}

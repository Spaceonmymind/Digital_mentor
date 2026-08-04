from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AnalysisStatus = Literal["queued", "processing", "completed", "failed", "cancelled"]


class AnalysisCreateRequest(BaseModel):
    document_id: str = Field(min_length=1)
    analysis_type: Literal["mentor"] = "mentor"
    methodology_id: str = Field(default="mentor-default", min_length=1, max_length=100)
    methodology_version: str = Field(default="draft", min_length=1, max_length=100)


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus


class AnalysisStatusResponse(BaseModel):
    id: str
    document_id: str
    analysis_type: str
    status: AnalysisStatus
    progress: int = Field(ge=0, le=100)
    current_step: str | None
    message: str | None = None
    error_message: str | None = None


class AnalysisEventResponse(BaseModel):
    id: str
    analysis_id: str
    step_code: str
    status: str
    progress: int
    message: str
    created_at: datetime

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


AnalysisStatus = Literal["queued", "processing", "completed", "failed", "cancelled"]
AnalysisMode = Literal["demo", "standard", "expert"]


class AnalysisCreateRequest(BaseModel):
    document_id: str = Field(min_length=1)
    analysis_type: Literal["mentor"] = "mentor"
    methodology_id: str = Field(default="mentor-default", min_length=1, max_length=100)
    methodology_version: str = Field(default="draft", min_length=1, max_length=100)
    mode: AnalysisMode = "standard"


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
    mode: AnalysisMode = "standard"


class AnalysisEventResponse(BaseModel):
    id: str
    analysis_id: str
    step_code: str
    status: str
    progress: int
    message: str
    created_at: datetime


class AnalysisHistoryItem(BaseModel):
    analysis_id: str
    document_id: str
    document_name: str
    mime_type: str
    status: AnalysisStatus
    methodology_id: str
    methodology_version: str
    mode: AnalysisMode
    overall_score: int | None = None
    total_score_max: int | None = None
    report_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AnalysisHistoryResponse(BaseModel):
    items: list[AnalysisHistoryItem]
    total: int
    limit: int
    offset: int


class AnalysisMetricAgent(BaseModel):
    agent_code: str | None
    model: str
    provider: str | None = None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    cost_rub: Decimal | None = None
    status: str


class AnalysisMetricsResponse(BaseModel):
    processing_time_ms: int
    methodology: dict[str, str]
    agents_count: int
    llm_calls_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    cost_rub: Decimal
    models: list[str]
    providers: list[str]
    agents: list[AnalysisMetricAgent]


class AnalysisEvidenceItem(BaseModel):
    criterion_code: str | None = None
    document_id: str
    page: int | None = None
    section: str | None = None
    quote: str | None = None
    block_index: int | None = None
    bbox: list[float] | None = None
    page_width: float | None = None
    page_height: float | None = None
    source_type: Literal["pdf", "docx"]
    match_status: Literal["exact", "page_only", "fragment"]
    extra: dict[str, Any] = {}

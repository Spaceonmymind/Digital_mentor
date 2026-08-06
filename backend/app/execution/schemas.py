from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str | None = None
    page: int | None = None
    section: str | None = None
    explanation: str = Field(..., min_length=1)


class WorkerIndicatorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["satisfied", "partially_satisfied", "not_satisfied", "insufficient_data"]
    score: int = Field(..., ge=0, le=100)
    summary: str = Field(..., min_length=1)
    strengths: list[str]
    issues: list[str]
    evidence: list[EvidenceItem]
    recommendations: list[str]
    confidence: float = Field(..., ge=0, le=1)

    @model_validator(mode="after")
    def validate_insufficient_data_explanation(self):
        if self.status == "insufficient_data" and not self.summary.strip():
            raise ValueError("insufficient_data requires explanation in summary")
        return self


class TaskRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assessment_id: str
    criterion_id: str
    indicator_id: str
    prompt_template_id: str
    status: str
    attempt: int
    error_code: str | None
    llm_call_id: str | None
    idempotency_key: str


class WorkerExecutionResult(BaseModel):
    task_run_id: str
    indicator_result_id: str | None = None
    status: str
    cache_hit: bool = False
    llm_call_id: str | None = None
    tokens: int = 0
    cost_rub: Decimal | None = None
    provider: str | None = None
    latency_ms: int = 0


class AssessmentExecutionSummary(BaseModel):
    assessment_id: str
    status: str
    tasks_total: int
    tasks_completed: int
    tasks_failed: int
    current_task: dict | None = None


class IndicatorResultListItem(BaseModel):
    id: str
    assessment_id: str
    assessment_result_id: str
    methodology_indicator_id: str
    status: str
    score: Decimal | None
    summary: str | None
    evidence_json: list
    recommendations_json: list
    confidence: Decimal | None
    prompt_template_id: str | None
    prompt_version: str | None
    llm_call_id: str | None
    created_at: str

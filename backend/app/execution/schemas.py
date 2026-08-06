from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class DisputedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_finding: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    evidence: list[EvidenceItem]


class CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["accepted", "revise", "rejected", "insufficient_data"]
    worker_result_supported: bool
    confirmed_findings: list[str]
    disputed_findings: list[DisputedFinding]
    missed_issues: list[str]
    contradictions: list[str]
    recommended_adjustments: list[str]
    confidence: float

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class PriorityRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    expected_effect: str = Field(..., min_length=1)
    difficulty: Literal["low", "medium", "high"]

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: int) -> int:
        if value < 1:
            raise ValueError("priority must be greater than or equal to 1")
        return value


class CriterionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    evidence_references: list[str]


class FinalExpertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_status: Literal["strong", "acceptable", "requires_revision", "insufficient_data"]
    overall_score: int | None
    executive_summary: str = Field(..., min_length=1)
    strengths: list[str]
    key_issues: list[str]
    contradictions: list[str]
    priority_recommendations: list[PriorityRecommendation]
    criterion_summaries: list[CriterionSummary]
    questions_to_author: list[str]
    limitations: list[str]
    confidence: float

    @field_validator("overall_score")
    @classmethod
    def validate_overall_score(cls, value: int | None) -> int | None:
        if value is not None and (value < 0 or value > 100):
            raise ValueError("overall_score must be between 0 and 100")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


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


class AgentExecutionResult(BaseModel):
    task_run_id: str
    agent_result_id: str | None = None
    agent_code: str
    model_role: str
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


class MentorAgentTraceItem(BaseModel):
    agent_code: str
    agent_version: str
    model_role: str
    llm_call_id: str | None
    evidence_references: list[str]


class MentorCriterionResult(BaseModel):
    criterion: str
    status: str
    summary: str
    indicators: list[dict]
    provenance: list[MentorAgentTraceItem]


class MentorAnalysisResultPayload(BaseModel):
    assessment_id: str
    document_id: str
    methodology_code: str
    methodology_version: str
    status: str
    overall_score: int | None = None
    executive_summary: str
    criteria: list[MentorCriterionResult]
    strengths: list[str]
    issues: list[str]
    contradictions: list[str]
    recommendations: list[PriorityRecommendation]
    questions_to_author: list[str]
    agent_trace: list[MentorAgentTraceItem]
    total_tokens: int
    total_cost_rub: Decimal | None = None
    processing_time_ms: int
    limitations: list[str]

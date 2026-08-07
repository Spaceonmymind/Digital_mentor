from __future__ import annotations

import re
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


class ReportHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_title: str = Field(..., min_length=1)
    work_type: str = Field(..., min_length=1)
    analysis_date: str = Field(..., min_length=1)
    work_version: str | None
    methodology: str = Field(..., min_length=1)
    current_stage: str = Field(..., pattern=r"^S[0-9]$")


class VetoBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool
    reason: str | None
    why_further_assessment_is_meaningless: str | None
    how_to_remove: str | None

    @model_validator(mode="after")
    def validate_active_veto(self):
        if self.is_active:
            for field_name in ("reason", "why_further_assessment_is_meaningless", "how_to_remove"):
                value = getattr(self, field_name)
                if not value or not value.strip():
                    raise ValueError("active veto requires reason, why_further_assessment_is_meaningless and how_to_remove")
        return self


class Objection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    what_does_not_work: str = Field(..., min_length=1)
    why: str = Field(..., min_length=1)
    where_to_move: str = Field(..., min_length=1)


class SingleQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1)


class SingleNextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str = Field(..., min_length=1)
    check_result: str = Field(..., min_length=1)


class StageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_code: str = Field(..., pattern=r"^S[0-9]$")
    title: str = Field(..., min_length=1)
    score: int
    completed: str = Field(..., min_length=1)
    next_level_requirement: str = Field(..., min_length=1)

    @field_validator("score")
    @classmethod
    def validate_stage_score(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("stage score must be between 0 and 5")
        return value


class MentorBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leading_blind_spot: str = Field(..., min_length=1)
    what_changed: str = Field(..., min_length=1)
    what_remains_unresolved: str = Field(..., min_length=1)
    mentor_question: str = Field(..., min_length=1)
    recommended_intervention: str = Field(..., min_length=1)


class MentorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: ReportHeader
    what_this_work_is: str = Field(..., min_length=1)
    veto: VetoBlock
    what_survived: list[str]
    objections: list[Objection]
    one_question: SingleQuestion
    one_next_step: SingleNextStep
    stage_assessments: list[StageAssessment]
    mentor_block: MentorBlock
    spoken_summary: str = Field(..., min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_p112(self):
        if not self.what_survived:
            raise ValueError("what_survived is required")
        if len(self.objections) > 5:
            raise ValueError("objections must contain no more than 5 items")
        if not self.stage_assessments:
            raise ValueError("stage_assessments is required")
        text = self.model_dump_json()
        normalized = text.lower()
        forbidden_substrings = [
            "quote_not_found",
            "llmcall",
            "assessment id",
            "mockanalysisengine",
            "uuid",
            "идентификатор assessment",
        ]
        forbidden_patterns = [
            r"\bworker\b",
            r"\bcritic\b",
            r"\bprovider\b",
            r"\btokens\b",
            r"\bcost\b",
            r"\btotal_tokens\b",
            r"\btotal_cost_rub\b",
            r"\bllm\b",
        ]
        if any(value in normalized for value in forbidden_substrings):
            raise ValueError("user-facing report contains internal terms")
        if any(re.search(pattern, normalized) for pattern in forbidden_patterns):
            raise ValueError("user-facing report contains internal terms")
        if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.IGNORECASE):
            raise ValueError("user-facing report contains UUID")
        if re.search(r"\bA-\d{2}\b", text):
            raise ValueError("user-facing report contains internal agent code")
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


class TechnicalAssessmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    document_id: str
    methodology_code: str
    methodology_version: str
    anti_during_method_version: str
    anti_during_implementation_version: str
    agent_trace: list[MentorAgentTraceItem]
    worker_results: list[dict]
    critic_results: list[dict]
    final_result: dict
    evidence_diagnostics: list[dict]
    total_tokens: int
    total_cost_rub: Decimal | None = None
    processing_time_ms: int


class DemoAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, max_length=500)
    strengths: list[str]
    issues: list[str]
    recommendations: list[str]
    score: int = Field(..., ge=0, le=10)

    @model_validator(mode="after")
    def limit_demo_lists(self):
        self.strengths = self.strengths[:3]
        self.issues = self.issues[:3]
        self.recommendations = self.recommendations[:3]
        return self


class DemoCriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["Проблема", "Решение", "Архитектура", "Экономика", "Риски", "Инновационность"]
    score: int = Field(..., ge=0, le=10)
    comment: str = Field(..., min_length=1, max_length=500)


class DemoFinalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: int = Field(..., ge=0, le=60)
    criteria: list[DemoCriterionScore]
    strengths: list[str]
    remarks: list[str]
    recommendations: list[str]
    conclusion: str = Field(..., min_length=1, max_length=500)
    spoken_summary: str = Field(..., min_length=1, max_length=700)

    @model_validator(mode="after")
    def validate_score_sum(self):
        if len(self.criteria) != 6:
            raise ValueError("demo final report requires exactly 6 criteria")
        self.strengths = self.strengths[:3]
        self.remarks = self.remarks[:3]
        self.recommendations = self.recommendations[:3]
        total = sum(item.score for item in self.criteria)
        if self.overall_score != total:
            raise ValueError("overall_score must equal sum of criteria scores")
        return self


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
    report: MentorReport | None = None
    technical: TechnicalAssessmentResult | None = None
    spoken_summary: str | None = None

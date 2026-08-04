from typing import Any

from pydantic import BaseModel

from app.schemas.methodology import AgentTraceItem, AnalysisEvidence, MethodologyReference


class CriterionResult(BaseModel):
    code: str
    title: str
    score: int
    max_score: int = 100
    explanation: str


class RemarkResult(BaseModel):
    id: str | None = None
    title: str
    quote: str
    recommendation: str
    page: int | None = None
    section: str | None = None
    severity: str | None = None
    comment: str | None = None
    priority: str | None = None
    page_number: int | None = None
    block_index: int | None = None
    evidence: list[AnalysisEvidence] = []


class AiRiskResult(BaseModel):
    level: str
    score: int | None = None
    factors: list[str]
    disclaimer: str


class RecommendationResult(BaseModel):
    priority: str
    title: str
    effect: str
    complexity: str


class AnalysisResultPayload(BaseModel):
    analysis_id: str
    overall_score: int
    verdict: str
    criteria: list[CriterionResult]
    strengths: list[str]
    improvements: list[str]
    remarks: list[RemarkResult]
    ai_risk: AiRiskResult
    recommendations: list[RecommendationResult]
    trace: list[dict[str, Any] | AgentTraceItem] = []
    methodology: MethodologyReference | None = None
    evidence: list[AnalysisEvidence] = []
    extra_blocks: dict[str, Any] = {}

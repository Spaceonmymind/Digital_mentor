from typing import Any

from pydantic import BaseModel


class CriterionResult(BaseModel):
    code: str
    title: str
    score: int
    max_score: int = 100
    explanation: str


class RemarkResult(BaseModel):
    title: str
    quote: str
    recommendation: str
    page_number: int | None = None
    block_index: int | None = None


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
    trace: list[dict[str, Any]] = []

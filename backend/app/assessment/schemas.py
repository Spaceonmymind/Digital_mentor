from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreateAssessment(BaseModel):
    artifact_type: str = Field(..., min_length=1, max_length=64)
    artifact_id: str = Field(..., min_length=1, max_length=36)
    methodology_id: str = Field(..., min_length=1, max_length=36)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    artifact_type: str
    artifact_id: str
    methodology_id: str
    status: str
    created_at: datetime


class IndicatorResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assessment_result_id: str
    methodology_indicator_id: str
    status: str
    score: Decimal | None
    summary: str | None
    evidence: str | None
    evidence_json: list
    recommendation: str | None
    recommendations_json: list
    confidence: Decimal | None
    prompt_template_id: str | None
    prompt_version: str | None
    llm_call_id: str | None
    created_at: datetime


class AssessmentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assessment_id: str
    methodology_criterion_id: str
    severity: str | None
    score: Decimal | None
    status: str
    summary: str | None
    created_at: datetime
    indicator_results: list[IndicatorResultResponse] = []

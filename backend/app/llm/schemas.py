from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_rub: Decimal | None = None


class LLMResult(BaseModel, Generic[T]):
    output: T
    provider_response_id: str | None = None
    requested_model: str
    actual_model: str | None = None
    aggregator: str
    provider: str
    finish_reason: str | None = None
    temperature: float | None = None
    max_completion_tokens: int | None = None
    seed: int | None = None
    usage: LLMUsage
    latency_ms: int
    status: str = "success"


class LLMCallTraceCreate(BaseModel):
    provider_response_id: str | None = None
    requested_model: str
    actual_model: str | None = None
    aggregator: str
    provider: str | None = None
    finish_reason: str | None = None
    temperature: float | None = None
    max_completion_tokens: int | None = None
    seed: int | None = None
    analysis_id: str | None = None
    assessment_id: str | None = None
    task_run_id: str | None = None
    agent_task_run_id: str | None = None
    methodology_agent_id: str | None = None
    agent_code: str | None = None
    stage_code: str | None = None
    criterion_id: str | None = None
    indicator_id: str | None = None
    prompt_template_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_rub: Decimal | None = None
    latency_ms: int = 0
    status: str


class LLMTestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    system_prompt: str = Field(
        default="Ты помогаешь кратко структурировать описание идеи. Верни только JSON по схеме.",
        min_length=1,
    )


class LLMTestStructuredResponse(BaseModel):
    summary: str
    keywords: list[str]


class LLMTestNestedRisk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    score: int = Field(..., ge=0, le=10)
    note: str | None = None


class LLMTestNestedSection(BaseModel):
    name: str
    risks: list[LLMTestNestedRisk]


class LLMTestNestedStructuredResponse(BaseModel):
    summary: str
    section: LLMTestNestedSection
    items: list[LLMTestNestedRisk]


class LLMTestResponse(BaseModel):
    summary: str
    keywords: list[str]
    tokens: int
    cost_rub: Decimal | None = None
    provider: str
    requested_model: str
    actual_model: str | None = None
    provider_response_id: str | None = None
    latency_ms: int


class LLMCallTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    provider_response_id: str | None
    requested_model: str
    actual_model: str | None
    aggregator: str
    provider: str
    finish_reason: str | None
    temperature: float | None
    max_completion_tokens: int | None
    seed: int | None
    analysis_id: str | None
    assessment_id: str | None
    task_run_id: str | None
    agent_task_run_id: str | None = None
    methodology_agent_id: str | None = None
    agent_code: str | None = None
    stage_code: str | None = None
    criterion_id: str | None
    indicator_id: str | None
    prompt_template_id: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    cost_rub: Decimal | None
    latency_ms: int
    status: str
    created_at: datetime

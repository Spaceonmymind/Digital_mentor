from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MethodologyCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    version: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True
    work_type_code: str | None = Field(default=None, max_length=64)
    status: str = Field(default="ACTIVE", max_length=32)
    max_score: int | None = Field(default=None, ge=0)
    applicable_formats: list[str] = Field(default_factory=lambda: ["pdf", "docx"])
    configuration: dict = Field(default_factory=dict)


class MethodologyIndicatorResponse(BaseModel):
    id: str
    title: str
    description: str | None
    expected_result: str | None
    weight: Decimal | None
    order_index: int
    required: bool = True
    configuration: dict = Field(default_factory=dict)
    is_demo: bool
    source: str | None = None
    version: str | None = None


class MethodologyCriterionResponse(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    weight: Decimal | None
    max_score: int | None = None
    required: bool = True
    configuration: dict = Field(default_factory=dict)
    order_index: int
    is_demo: bool
    source: str | None = None
    version: str | None = None
    indicators: list[MethodologyIndicatorResponse]


class PromptTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    methodology_id: str
    stage: str
    system_prompt: str
    user_template: str
    version: str
    is_demo: bool
    source: str | None = None


class MethodologyAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    methodology_id: str
    code: str
    name: str
    version: str
    stage_code: str
    execution_order: int
    execution_mode: str
    model_role: str
    prompt_template_id: str | None
    input_schema_code: str | None
    output_schema_code: str | None
    is_active: bool
    is_required: bool
    source: str | None = None
    is_demo: bool
    configuration: dict = Field(default_factory=dict)


class MethodologyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None
    version: str
    is_active: bool
    is_demo: bool
    source: str | None = None
    work_type_code: str | None = None
    status: str = "ACTIVE"
    max_score: int | None = None
    applicable_formats: list[str] = Field(default_factory=list)
    configuration: dict = Field(default_factory=dict)
    created_at: datetime


class MethodologyFullResponse(MethodologyResponse):
    criteria: list[MethodologyCriterionResponse]
    prompts: list[PromptTemplateResponse]
    agents: list[MethodologyAgentResponse] = []


class ActiveMethodologySummary(BaseModel):
    methodology_id: str
    name: str
    version: str
    max_score: int | None = None
    criteria_count: int


class WorkTypeCatalogItem(BaseModel):
    work_type: str
    display_name: str
    description: str
    availability: str
    active_methodology: ActiveMethodologySummary | None = None
    active_version: str | None = None
    max_score: int | None = None

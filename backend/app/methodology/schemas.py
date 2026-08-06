from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MethodologyCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    version: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True


class MethodologyIndicatorResponse(BaseModel):
    id: str
    title: str
    description: str | None
    expected_result: str | None
    weight: Decimal
    order_index: int
    is_demo: bool


class MethodologyCriterionResponse(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    weight: Decimal
    order_index: int
    is_demo: bool
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


class MethodologyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None
    version: str
    is_active: bool
    is_demo: bool
    created_at: datetime


class MethodologyFullResponse(MethodologyResponse):
    criteria: list[MethodologyCriterionResponse]
    prompts: list[PromptTemplateResponse]

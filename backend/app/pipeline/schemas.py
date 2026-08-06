from pydantic import BaseModel, Field


class PipelineBuildRequest(BaseModel):
    artifact_type: str | None = Field(default=None, max_length=128)
    artifact_id: str = Field(..., min_length=1, max_length=36)
    filename: str = ""
    metadata: dict = Field(default_factory=dict)


class AssessmentTask(BaseModel):
    criterion_id: str
    indicator_id: str
    methodology_id: str
    prompt_template_id: str
    criterion: str
    indicator: str


class AssessmentPlan(BaseModel):
    assessment_id: str
    tasks: list[AssessmentTask]


class PipelineBuildResponse(BaseModel):
    assessment_id: str
    methodology: str
    tasks_count: int
    tasks: list[AssessmentTask]

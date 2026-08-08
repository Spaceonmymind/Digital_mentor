from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.repository import AssessmentRepository
from app.methodology.repository import MethodologyRepository
from app.pipeline.artifact_resolver import ArtifactResolver
from app.pipeline.methodology_resolver import MethodologyResolver
from app.pipeline.plan_builder import PlanBuilder
from app.pipeline.schemas import PipelineBuildRequest, PipelineBuildResponse


class PipelineService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.artifact_resolver = ArtifactResolver()
        self.methodology_resolver = MethodologyResolver(MethodologyRepository(session))
        self.assessment_repository = AssessmentRepository(session)
        self.plan_builder = PlanBuilder(session)

    async def build(self, payload: PipelineBuildRequest) -> PipelineBuildResponse:
        artifact_type = await self.artifact_resolver.resolve(
            artifact_type=payload.artifact_type,
            filename=payload.filename,
            metadata=payload.metadata,
        )
        methodology = await self.methodology_resolver.resolve(artifact_type)
        assessment = await self.assessment_repository.create_assessment(
            artifact_type=artifact_type,
            artifact_id=payload.artifact_id,
            methodology_id=methodology.id,
        )
        plan = await self.plan_builder.build(assessment.id)
        return PipelineBuildResponse(
            assessment_id=plan.assessment_id,
            methodology=methodology.code,
            tasks_count=len(plan.tasks),
            tasks=plan.tasks,
        )

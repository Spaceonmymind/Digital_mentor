from app.assessment.models import Assessment
from app.assessment.repository import AssessmentRepository
from app.assessment.schemas import CreateAssessment


class AssessmentService:
    def __init__(self, repository: AssessmentRepository):
        self.repository = repository

    async def create_assessment(self, payload: CreateAssessment) -> Assessment:
        return await self.repository.create_assessment(
            artifact_type=payload.artifact_type,
            artifact_id=payload.artifact_id,
            methodology_id=payload.methodology_id,
        )

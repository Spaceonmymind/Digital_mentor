from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.repository import AssessmentRepository
from app.assessment.schemas import AssessmentResponse, CreateAssessment
from app.assessment.service import AssessmentService
from app.db.session import get_session


router = APIRouter(prefix="/api/v1/internal/assessment", tags=["internal-assessment"])


@router.post("", response_model=AssessmentResponse)
async def create_assessment(
    payload: CreateAssessment,
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    service = AssessmentService(AssessmentRepository(session))
    assessment = await service.create_assessment(payload)
    return AssessmentResponse.model_validate(assessment)

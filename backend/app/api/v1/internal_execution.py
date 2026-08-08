from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.execution.schemas import AssessmentExecutionSummary, IndicatorResultListItem
from app.execution.service import AssessmentExecutionService


router = APIRouter(prefix="/api/v1/internal/assessments", tags=["internal-assessment-execution"])


@router.post("/{assessment_id}/execute", response_model=AssessmentExecutionSummary)
async def execute_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> AssessmentExecutionSummary:
    return await AssessmentExecutionService(session).execute(assessment_id)


@router.get("/{assessment_id}/execution", response_model=AssessmentExecutionSummary)
async def get_assessment_execution(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> AssessmentExecutionSummary:
    return await AssessmentExecutionService(session).status(assessment_id)


@router.get("/{assessment_id}/indicator-results", response_model=list[IndicatorResultListItem])
async def get_assessment_indicator_results(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[IndicatorResultListItem]:
    return await AssessmentExecutionService(session).indicator_results(assessment_id)

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.execution.startup_vkr import StartupVkrAgentFlow


router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])


@router.get("/{assessment_id}/result")
async def get_assessment_result(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await StartupVkrAgentFlow(session).student_result(assessment_id)


@router.get("/{assessment_id}/progress")
async def get_assessment_progress(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await StartupVkrAgentFlow(session).progress(assessment_id)

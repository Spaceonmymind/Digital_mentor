from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.execution.schemas import MentorAnalysisResultPayload
from app.execution.startup_vkr import StartupVkrAgentFlow


router = APIRouter(prefix="/api/v1/internal/assessments", tags=["internal-assessment-gates"])


class GateReturnRequest(BaseModel):
    reason: str | None = None


@router.get("/{assessment_id}/gates/current")
async def get_current_gate(assessment_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await StartupVkrAgentFlow(session).current_gate(assessment_id)


@router.post("/{assessment_id}/gates/{gate_code}/approve")
async def approve_gate(assessment_id: str, gate_code: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await StartupVkrAgentFlow(session).decide_gate(assessment_id, gate_code, "approved")


@router.post("/{assessment_id}/gates/{gate_code}/return")
async def return_gate(
    assessment_id: str,
    gate_code: str,
    payload: GateReturnRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await StartupVkrAgentFlow(session).decide_gate(
        assessment_id,
        gate_code,
        "returned",
        reason=payload.reason if payload else None,
    )


@router.post("/{assessment_id}/resume", response_model=MentorAnalysisResultPayload)
async def resume_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> MentorAnalysisResultPayload:
    return await StartupVkrAgentFlow(session).resume(assessment_id)


@router.post("/{assessment_id}/retry-failed", response_model=MentorAnalysisResultPayload)
async def retry_failed_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
) -> MentorAnalysisResultPayload:
    return await StartupVkrAgentFlow(session).retry_failed(assessment_id)

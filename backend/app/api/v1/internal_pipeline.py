from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.pipeline.schemas import PipelineBuildRequest, PipelineBuildResponse
from app.pipeline.service import PipelineService


router = APIRouter(prefix="/api/v1/internal/pipeline", tags=["internal-pipeline"])


@router.post("/build", response_model=PipelineBuildResponse)
async def build_pipeline(
    payload: PipelineBuildRequest,
    session: AsyncSession = Depends(get_session),
) -> PipelineBuildResponse:
    return await PipelineService(session).build(payload)

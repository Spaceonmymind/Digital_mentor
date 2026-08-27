from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.tts import TtsRequest, TtsResponse
from app.db.session import get_session
from app.services.tts import get_tts_provider
from app.services.tts_service import TtsGenerationResult, TtsService


router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


def _response(result: TtsGenerationResult) -> TtsResponse:
    return TtsResponse(
        status=result.status,
        audio_id=result.audio_id,
        format=result.format,
        duration_ms=result.duration_ms,
        audio_url=result.audio_url,
        provider=result.provider,
        source=result.source,
        attempts=result.attempts,
        latency_ms=result.latency_ms,
        error_code=result.error_code,
    )


@router.post("", response_model=TtsResponse)
async def synthesize(payload: TtsRequest) -> TtsResponse:
    result = await get_tts_provider().synthesize(payload.text, payload.voice_id)
    return _response(result)


@router.post("/analyses/{analysis_id}", response_model=TtsResponse)
async def synthesize_analysis_summary(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> TtsResponse:
    result = await TtsService().synthesize_analysis_summary(session, analysis_id)
    return _response(result)

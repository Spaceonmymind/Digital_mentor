from fastapi import APIRouter

from app.schemas.tts import TtsRequest, TtsResponse
from app.services.tts import get_tts_provider


router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


@router.post("", response_model=TtsResponse)
async def synthesize(payload: TtsRequest) -> TtsResponse:
    result = await get_tts_provider().synthesize(payload.text, payload.voice_id)
    return TtsResponse(
        audio_id=result.audio_id,
        format=result.format,
        duration_ms=result.duration_ms,
        audio_url=result.audio_url,
        provider=result.provider,
    )

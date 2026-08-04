from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.errors import AppError
from app.services.storage import DocumentStorage


router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/audio/{audio_id}")
async def get_audio(audio_id: str) -> FileResponse:
    path = DocumentStorage().audio_path(audio_id)
    if not path.exists():
        raise AppError("TTS_UNAVAILABLE", "Аудиофайл не найден", status_code=404)
    return FileResponse(path, media_type="audio/mpeg", filename=f"{audio_id}.mp3")

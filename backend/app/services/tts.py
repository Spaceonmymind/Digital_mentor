from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AppError
from app.services.storage import DocumentStorage


class TtsResult(BaseModel):
    audio_id: str
    format: str
    duration_ms: int
    audio_url: str
    provider: str
    path: Path


class TtsProvider(Protocol):
    async def synthesize(self, text: str, voice_id: str | None = None) -> TtsResult:
        ...


class StubTtsProvider:
    async def synthesize(self, text: str, voice_id: str | None = None) -> TtsResult:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            raise AppError("TTS_UNAVAILABLE", "Нет текста для озвучивания", status_code=422)
        if len(normalized) > settings.tts_max_text_length:
            normalized = normalized[: settings.tts_max_text_length]

        audio_id = str(uuid4())
        path = DocumentStorage().audio_path(audio_id)
        # Stub payload: browser fallback remains the real audible option until a provider is approved.
        path.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00")
        return TtsResult(
            audio_id=audio_id,
            format="mp3",
            duration_ms=max(900, min(8000, len(normalized) * 55)),
            audio_url=f"/api/v1/media/audio/{audio_id}",
            provider="stub",
            path=path,
        )


class RemoteTtsProvider:
    async def synthesize(self, text: str, voice_id: str | None = None) -> TtsResult:
        raise AppError("TTS_UNAVAILABLE", "Серверный TTS-провайдер не подключен", status_code=503)


def get_tts_provider() -> TtsProvider:
    if settings.tts_mode == "remote":
        return RemoteTtsProvider()
    return StubTtsProvider()

from typing import Protocol

from app.services.tts_service import TtsGenerationResult, TtsService


TtsResult = TtsGenerationResult


class TtsProvider(Protocol):
    async def synthesize(self, text: str, voice_id: str | None = None) -> TtsResult:
        ...


class PolzaTtsProvider:
    async def synthesize(self, text: str, voice_id: str | None = None) -> TtsResult:
        return await TtsService().synthesize_text(text)


def get_tts_provider() -> TtsProvider:
    return PolzaTtsProvider()

from typing import Protocol

from pydantic import BaseModel


class SttResult(BaseModel):
    text: str
    provider: str


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes) -> SttResult:
        ...

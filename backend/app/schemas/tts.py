from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    voice_id: str | None = Field(default="mentor-default", max_length=100)


class TtsResponse(BaseModel):
    status: str = "ready"
    audio_id: str | None
    format: str
    duration_ms: int
    audio_url: str | None
    provider: str
    source: str = "polza"
    attempts: int = 0
    latency_ms: int = 0
    error_code: str | None = None

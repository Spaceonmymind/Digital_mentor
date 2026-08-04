from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=700)
    voice_id: str | None = Field(default="mentor-default", max_length=100)


class TtsResponse(BaseModel):
    audio_id: str
    format: str
    duration_ms: int
    audio_url: str
    provider: str

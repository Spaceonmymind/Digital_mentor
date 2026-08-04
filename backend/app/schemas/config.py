from pydantic import BaseModel


class PublicConfigResponse(BaseModel):
    demo_mode: bool
    frontend_mock_mode: bool
    tts_mode: str

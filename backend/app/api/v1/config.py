from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
async def get_public_config() -> dict[str, bool | str]:
    return {
        "demo_mode": settings.demo_mode,
        "presentation_mode": settings.presentation_mode,
        "frontend_mock_mode": settings.frontend_mock_mode,
        "tts_mode": settings.tts_mode,
    }

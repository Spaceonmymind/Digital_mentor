from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session_factory


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
async def ready() -> dict[str, str]:
    async with async_session_factory() as session:
        await session.execute(text("select 1"))
    for directory in ("documents", "extracted", "reports"):
        path = Path(settings.storage_path) / directory
        path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return {"status": "not_ready"}
    return {
        "status": "ready",
        "app_env": settings.app_env,
        "analysis_engine": "mock" if settings.mock_analysis_enabled else "disabled",
        "tts_mode": settings.tts_mode,
    }

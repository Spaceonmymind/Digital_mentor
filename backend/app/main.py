from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api.v1.analyses import router as analyses_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging
from app.db.models import Analysis
from app.db.session import async_session_factory


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    async with async_session_factory() as session:
        await session.execute(
            update(Analysis)
            .where(Analysis.status.in_(["queued", "processing"]))
            .values(status="failed", error_message="PROCESS_INTERRUPTED")
        )
        await session.commit()
    logger.info("backend_started env=%s", settings.app_env)
    yield


app = FastAPI(title="Digital Mentor API", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if "*" in settings.cors_origins else list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(health_router, prefix="/api/v1")
app.include_router(documents_router)
app.include_router(analyses_router)
app.include_router(chat_router)

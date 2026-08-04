from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import update

from app.api.v1.analyses import router as analyses_router
from app.api.v1.chat import router as chat_router
from app.api.v1.config import router as config_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.media import router as media_router
from app.api.v1.tts import router as tts_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.db.models import Analysis
from app.db.session import async_session_factory


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    for attempt in range(1, 16):
        try:
            async with async_session_factory() as session:
                await session.execute(
                    update(Analysis)
                    .where(Analysis.status.in_(["queued", "processing"]))
                    .values(status="failed", error_message="PROCESS_INTERRUPTED")
                )
                await session.commit()
            break
        except Exception:
            if attempt == 15:
                raise
            logger.warning("database_not_ready attempt=%s", attempt)
            await asyncio.sleep(2)
    logger.info("backend_started env=%s", settings.app_env)
    yield


app = FastAPI(title="Digital Mentor API", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Некорректные входные данные",
                "details": exc.errors(),
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id} if request_id else None,
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("internal_error request_id=%s", getattr(request.state, "request_id", None))
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка сервера",
                "details": None,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )

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
app.include_router(tts_router)
app.include_router(media_router)
app.include_router(config_router)

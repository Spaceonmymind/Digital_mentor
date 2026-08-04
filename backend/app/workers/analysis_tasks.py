import logging

from sqlalchemy import select

from app.db.models import Analysis
from app.db.session import async_session_factory
from app.services.mock_analysis_engine import get_analysis_engine

logger = logging.getLogger(__name__)


async def run_analysis_task(analysis_id: str) -> None:
    async with async_session_factory() as session:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            logger.error("analysis_task_missing analysis_id=%s", analysis_id)
            return
        document_id = analysis.document_id
        methodology_id = analysis.methodology_id
        methodology_version = analysis.methodology_version

    try:
        engine = get_analysis_engine()
        await engine.run(analysis_id, document_id, methodology_id, methodology_version)
    except Exception as exc:
        logger.exception("analysis_failed analysis_id=%s", analysis_id)
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is not None and analysis.status != "cancelled":
                analysis.status = "failed"
                analysis.error_message = str(exc)
                await session.commit()

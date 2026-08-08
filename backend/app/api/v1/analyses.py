import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import get_session
from app.schemas.analyses import AnalysisCreateRequest, AnalysisCreateResponse, AnalysisEventResponse, AnalysisStatusResponse
from app.schemas.reports import ReportResponse
from app.schemas.results import AnalysisResultPayload
from app.services.reports import ReportService
from app.services.storage import DocumentStorage
from app.workers.analysis_tasks import run_analysis_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


async def _latest_message(session: AsyncSession, analysis_id: str) -> str | None:
    result = await session.execute(
        select(AnalysisEvent)
        .where(AnalysisEvent.analysis_id == analysis_id)
        .order_by(AnalysisEvent.created_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    return event.message if event else None


def _status_response(analysis: Analysis, message: str | None = None) -> AnalysisStatusResponse:
    return AnalysisStatusResponse(
        id=analysis.id,
        document_id=analysis.document_id,
        analysis_type=analysis.analysis_type,
        status=analysis.status,
        progress=analysis.progress,
        current_step=analysis.current_step,
        message=message,
        error_message=analysis.error_message,
        mode=analysis.mode,
    )


@router.post("", response_model=AnalysisCreateResponse)
async def create_analysis(
    payload: AnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> AnalysisCreateResponse:
    document = await session.get(Document, payload.document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    if document.extraction_status != "completed":
        raise AppError("DOCUMENT_NOT_READY", "Текст документа еще не извлечен", status_code=409)

    analysis = Analysis(
        document_id=payload.document_id,
        analysis_type=payload.analysis_type,
        mode=payload.mode,
        methodology_id=payload.methodology_id,
        methodology_version=payload.methodology_version,
        status="queued",
        progress=0,
        current_step="queued",
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    logger.info("analysis_created analysis_id=%s document_id=%s", analysis.id, document.id)
    background_tasks.add_task(run_analysis_task, analysis.id)
    return AnalysisCreateResponse(analysis_id=analysis.id, status=analysis.status)


@router.get("/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis(analysis_id: str, session: AsyncSession = Depends(get_session)) -> AnalysisStatusResponse:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    return _status_response(analysis, await _latest_message(session, analysis_id))


@router.get("/{analysis_id}/result", response_model=AnalysisResultPayload)
async def get_analysis_result(analysis_id: str, session: AsyncSession = Depends(get_session)) -> AnalysisResultPayload:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    if analysis.status != "completed":
        raise AppError("ANALYSIS_NOT_COMPLETED", "Результат еще не сформирован", status_code=409)

    result = await session.execute(select(AnalysisResult).where(AnalysisResult.analysis_id == analysis_id))
    analysis_result = result.scalar_one_or_none()
    if analysis_result is None:
        raise AppError("ANALYSIS_RESULT_NOT_FOUND", "Результат анализа не найден", status_code=404)
    return AnalysisResultPayload.model_validate(analysis_result.result_json)


@router.get("/{analysis_id}/events")
async def get_analysis_events(analysis_id: str) -> StreamingResponse:
    async def event_stream():
        sent_event_ids = set()
        for _ in range(300):
            async for session in get_session():
                analysis = await session.get(Analysis, analysis_id)
                if analysis is None:
                    yield f"event: error\ndata: {json.dumps({'code': 'ANALYSIS_NOT_FOUND'}, ensure_ascii=False)}\n\n"
                    return
                query = select(AnalysisEvent).where(AnalysisEvent.analysis_id == analysis_id).order_by(AnalysisEvent.created_at)
                events = (await session.execute(query)).scalars().all()
                for event in events:
                    if event.id in sent_event_ids:
                        continue
                    sent_event_ids.add(event.id)
                    payload = AnalysisEventResponse(
                        id=event.id,
                        analysis_id=event.analysis_id,
                        step_code=event.step_code,
                        status=event.status,
                        progress=event.progress,
                        message=event.message,
                        created_at=event.created_at,
                    ).model_dump(mode="json")
                    yield f"event: analysis_event\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if analysis.status in {"completed", "failed", "cancelled"}:
                    yield f"event: analysis_status\ndata: {json.dumps({'status': analysis.status}, ensure_ascii=False)}\n\n"
                    return
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{analysis_id}/cancel", response_model=AnalysisStatusResponse)
async def cancel_analysis(analysis_id: str, session: AsyncSession = Depends(get_session)) -> AnalysisStatusResponse:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    if analysis.status in {"completed", "failed", "cancelled"}:
        return _status_response(analysis, await _latest_message(session, analysis_id))

    analysis.status = "cancelled"
    analysis.error_message = None
    session.add(
        AnalysisEvent(
            analysis_id=analysis_id,
            step_code=analysis.current_step or "cancelled",
            status="cancelled",
            progress=analysis.progress,
            message="Анализ отменен пользователем",
        )
    )
    await session.commit()
    await session.refresh(analysis)
    logger.info("analysis_cancel_requested analysis_id=%s", analysis_id)
    return _status_response(analysis, "Анализ отменен пользователем")


@router.post("/{analysis_id}/reports", response_model=ReportResponse)
async def create_report(analysis_id: str, session: AsyncSession = Depends(get_session)) -> ReportResponse:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    document = await session.get(Document, analysis.document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    result = (await session.execute(select(AnalysisResult).where(AnalysisResult.analysis_id == analysis_id))).scalar_one_or_none()
    if result is None:
        raise AppError("ANALYSIS_NOT_COMPLETED", "Результат еще не сформирован", status_code=409)
    try:
        report = ReportService().create_pdf_report(analysis, document, result)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("REPORT_GENERATION_FAILED", "Не удалось сформировать отчет", status_code=500) from exc
    logger.info("report_created analysis_id=%s report_id=%s", analysis_id, report.report_id)
    return report


@router.get("/{analysis_id}/reports/{report_id}")
async def get_report(analysis_id: str, report_id: str) -> FileResponse:
    path = DocumentStorage().report_path(analysis_id, report_id)
    if not path.exists():
        raise AppError("REPORT_NOT_FOUND", "Отчет не найден", status_code=404)
    return FileResponse(path, media_type="application/pdf", filename=f"digital-mentor-report-{report_id}.pdf")

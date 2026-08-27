import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse, StreamingResponse
from decimal import Decimal
from pathlib import Path

import fitz
from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, DetailedReport, Document, LLMCall
from app.execution.models import AgentResult, MentorAnalysisResult
from app.db.session import get_session
from app.schemas.analyses import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisEvidenceItem,
    AnalysisEventResponse,
    AnalysisHistoryItem,
    AnalysisHistoryResponse,
    AnalysisMetricAgent,
    AnalysisMetricsResponse,
    AnalysisStatusResponse,
)
from app.schemas.reports import DetailedReportStatusResponse, ReportResponse
from app.services.detailed_reports import (
    detailed_report_path,
    detailed_report_status,
    generate_detailed_report_task,
    get_detailed_report,
    get_or_create_detailed_report,
)
from app.schemas.results import AnalysisResultPayload
from app.services.reports import ReportService
from app.services.storage import DocumentStorage
from app.services.document_context import load_extracted_payload
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


@router.get("/history", response_model=AnalysisHistoryResponse)
async def get_analysis_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    methodology: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> AnalysisHistoryResponse:
    filters = [Document.deleted_at.is_(None)]
    if status:
        filters.append(Analysis.status == status)
    if methodology:
        filters.append(Analysis.methodology_id == methodology)
    total = (
        await session.execute(
            select(func.count()).select_from(Analysis).join(Document, Document.id == Analysis.document_id).where(*filters)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(Analysis, Document, AnalysisResult, DetailedReport)
            .join(Document, Document.id == Analysis.document_id)
            .outerjoin(AnalysisResult, AnalysisResult.analysis_id == Analysis.id)
            .outerjoin(DetailedReport, DetailedReport.analysis_id == Analysis.id)
            .where(*filters)
            .order_by(Analysis.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for analysis, document, result, report in rows:
        payload = result.result_json if result else {}
        extra = payload.get("extra_blocks") or {}
        items.append(
            AnalysisHistoryItem(
                analysis_id=analysis.id,
                document_id=document.id,
                document_name=document.original_name,
                mime_type=document.mime_type,
                status=analysis.status,
                methodology_id=analysis.methodology_id,
                methodology_version=analysis.methodology_version,
                mode=analysis.mode,
                overall_score=payload.get("overall_score"),
                total_score_max=extra.get("total_score_max", 60 if analysis.methodology_id == "STARTUP_VKR" else 100),
                report_url=report.report_url if report and report.status == "completed" else None,
                created_at=analysis.created_at,
                completed_at=analysis.completed_at,
            )
        )
    return AnalysisHistoryResponse(items=items, total=total, limit=limit, offset=offset)


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


@router.get("/{analysis_id}/metrics", response_model=AnalysisMetricsResponse)
async def get_analysis_metrics(analysis_id: str, session: AsyncSession = Depends(get_session)) -> AnalysisMetricsResponse:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    calls = (
        await session.execute(select(LLMCall).where(LLMCall.analysis_id == analysis_id).order_by(LLMCall.created_at))
    ).scalars().all()
    mentor_result = (
        await session.execute(select(MentorAnalysisResult).where(MentorAnalysisResult.analysis_id == analysis_id).limit(1))
    ).scalar_one_or_none()
    if mentor_result:
        processing_time_ms = mentor_result.processing_time_ms
    elif analysis.started_at and analysis.completed_at:
        processing_time_ms = max(0, int((analysis.completed_at - analysis.started_at).total_seconds() * 1000))
    else:
        processing_time_ms = sum(call.latency_ms for call in calls)
    agents = [
        AnalysisMetricAgent(
            agent_code=call.agent_code,
            model=call.actual_model or call.requested_model,
            provider=call.provider,
            latency_ms=call.latency_ms,
            input_tokens=call.prompt_tokens,
            output_tokens=call.completion_tokens,
            total_tokens=call.total_tokens,
            cached_tokens=call.cached_tokens,
            cost_rub=call.cost_rub,
            status=call.status,
        )
        for call in calls
    ]
    return AnalysisMetricsResponse(
        processing_time_ms=processing_time_ms,
        methodology={"id": analysis.methodology_id, "version": analysis.methodology_version},
        agents_count=len({call.agent_code for call in calls if call.agent_code}),
        llm_calls_count=len(calls),
        input_tokens=sum(call.prompt_tokens for call in calls),
        output_tokens=sum(call.completion_tokens for call in calls),
        total_tokens=sum(call.total_tokens for call in calls),
        cached_tokens=sum(call.cached_tokens for call in calls),
        cost_rub=sum((call.cost_rub or Decimal("0")) for call in calls),
        models=sorted({call.actual_model or call.requested_model for call in calls}),
        providers=sorted({call.provider for call in calls if call.provider}),
        agents=agents,
    )


def _locate_evidence(payload: dict, quote: str | None, section: str | None) -> tuple[int | None, int | None, list[float] | None, str]:
    normalized_quote = " ".join((quote or "").split()).lower()
    quote_prefix = normalized_quote.rstrip(".… ")
    for page in payload.get("pages") or []:
        for block in page.get("blocks") or []:
            block_text = " ".join(str(block.get("text") or "").split()).lower()
            if normalized_quote and (normalized_quote in block_text or (len(quote_prefix) >= 40 and quote_prefix in block_text)):
                return page.get("page_number"), block.get("block_index"), block.get("bbox"), "exact"
    normalized_section = (section or "").lower()
    for paragraph in payload.get("paragraphs") or []:
        text = str(paragraph.get("text") or "")
        if (normalized_quote and normalized_quote in " ".join(text.split()).lower()) or (
            normalized_section and normalized_section in text.lower()
        ):
            return None, paragraph.get("paragraph_index"), None, "fragment"
    return None, None, None, "page_only"


_EVIDENCE_TERMS = {
    "C1": ("проблем", "актуаль", "потребност", "цель"),
    "C2": ("продукт", "решени", "инновац", "новизн", "mvp", "технолог"),
    "C3": ("рынок", "аудитор", "клиент", "сегмент", "конкурент"),
    "C4": ("бизнес", "монетизац", "маркетинг", "продаж", "доход"),
    "C5": ("финанс", "затрат", "выруч", "окупаем", "инвестиц", "npv", "irr"),
    "C6": ("риск", "развити", "roadmap", "масштаб", "внедрен", "результат"),
}


def _fallback_pdf_evidence(payload: dict, criterion_code: str) -> tuple[int | None, int | None, list[float] | None, str | None]:
    terms = _EVIDENCE_TERMS.get(criterion_code, ())
    candidates = []
    for page in payload.get("pages") or []:
        for block in page.get("blocks") or []:
            text = " ".join(str(block.get("text") or "").split()).strip()
            if len(text) < 60 or not block.get("bbox"):
                continue
            normalized = text.lower()
            score = sum(1 for term in terms if term in normalized)
            candidates.append((score, len(text), page, block, text))
    if not candidates:
        return None, None, None, None
    _, _, page, block, text = max(candidates, key=lambda item: (item[0], item[1]))
    return page.get("page_number"), block.get("block_index"), block.get("bbox"), text[:300]


@router.get("/{analysis_id}/evidence", response_model=list[AnalysisEvidenceItem])
async def get_analysis_evidence(analysis_id: str, session: AsyncSession = Depends(get_session)) -> list[AnalysisEvidenceItem]:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    document = await session.get(Document, analysis.document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    mentor_result = (
        await session.execute(select(MentorAnalysisResult).where(MentorAnalysisResult.analysis_id == analysis_id).limit(1))
    ).scalar_one_or_none()
    assessment_id = mentor_result.assessment_id if mentor_result else (
        await session.execute(
            select(LLMCall.assessment_id)
            .where(LLMCall.analysis_id == analysis_id, LLMCall.assessment_id.is_not(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if assessment_id is None:
        return []
    agent_results = (
        await session.execute(select(AgentResult).where(AgentResult.assessment_id == assessment_id))
    ).scalars().all()
    extracted = load_extracted_payload(document)
    source_type = "pdf" if document.mime_type == "application/pdf" else "docx"
    page_sizes: dict[int, tuple[float, float]] = {}
    if source_type == "pdf" and Path(document.storage_path).exists():
        with fitz.open(document.storage_path) as pdf:
            page_sizes = {
                index + 1: (float(page.rect.width), float(page.rect.height))
                for index, page in enumerate(pdf)
            }
    items: list[AnalysisEvidenceItem] = []
    seen: set[tuple] = set()
    located_criteria: set[str] = set()
    for agent_result in agent_results:
        for criterion in agent_result.output_json.get("criteria") or []:
            for evidence in criterion.get("evidence") or []:
                quote = evidence.get("quote")
                section = evidence.get("section")
                if not quote and not section:
                    continue
                page, block_index, bbox, match_status = _locate_evidence(extracted, quote, section)
                if source_type == "pdf" and not page:
                    fallback_page, fallback_block_index, fallback_bbox, fallback_quote = _fallback_pdf_evidence(
                        extracted,
                        criterion.get("criterion_code") or "",
                    )
                    if fallback_page:
                        page = fallback_page
                        block_index = fallback_block_index
                        bbox = fallback_bbox
                        quote = quote or fallback_quote
                    else:
                        first_page = next(iter(extracted.get("pages") or []), {})
                        page = first_page.get("page_number")
                    match_status = "page_only"
                key = (criterion.get("criterion_code"), quote, section)
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    AnalysisEvidenceItem(
                        criterion_code=criterion.get("criterion_code"),
                        document_id=document.id,
                        page=page,
                        section=section,
                        quote=quote,
                        block_index=block_index,
                        bbox=bbox,
                        page_width=page_sizes.get(page, (None, None))[0] if page else None,
                        page_height=page_sizes.get(page, (None, None))[1] if page else None,
                        source_type=source_type,
                        match_status=match_status if source_type == "pdf" else "fragment",
                    )
                )
                if page and criterion.get("criterion_code"):
                    located_criteria.add(criterion.get("criterion_code"))
    if source_type == "pdf":
        for criterion_code in _EVIDENCE_TERMS:
            if criterion_code in located_criteria:
                continue
            page, block_index, bbox, quote = _fallback_pdf_evidence(extracted, criterion_code)
            if not page or not bbox or not quote:
                continue
            items.append(
                AnalysisEvidenceItem(
                    criterion_code=criterion_code,
                    document_id=document.id,
                    page=page,
                    section="Релевантный фрагмент исходного PDF",
                    quote=quote,
                    block_index=block_index,
                    bbox=bbox,
                    page_width=page_sizes.get(page, (None, None))[0],
                    page_height=page_sizes.get(page, (None, None))[1],
                    source_type="pdf",
                    match_status="page_only",
                    extra={"source": "deterministic_pdf_match"},
                )
            )
    return items


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


@router.post("/{analysis_id}/detailed-report", response_model=DetailedReportStatusResponse)
async def start_detailed_report(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> DetailedReportStatusResponse:
    report = await get_or_create_detailed_report(session, analysis_id)
    if report.status in {"pending", "failed"}:
        background_tasks.add_task(generate_detailed_report_task, analysis_id)
    return detailed_report_status(report, analysis_id)


@router.get("/{analysis_id}/detailed-report/status", response_model=DetailedReportStatusResponse)
async def get_detailed_report_status(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> DetailedReportStatusResponse:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    report = await get_detailed_report(session, analysis_id)
    return detailed_report_status(report, analysis_id)


@router.get("/{analysis_id}/detailed-report/download")
async def download_detailed_report(analysis_id: str, session: AsyncSession = Depends(get_session)) -> FileResponse:
    report = await get_detailed_report(session, analysis_id)
    if report is None or report.status != "completed":
        raise AppError("DETAILED_REPORT_NOT_READY", "Подробный отчет еще не готов", status_code=409)
    path = detailed_report_path(analysis_id, report)
    if not path.exists():
        raise AppError("REPORT_NOT_FOUND", "Отчет не найден", status_code=404)
    return FileResponse(path, media_type="application/pdf", filename=f"digital-mentor-detailed-report-{report.report_id}.pdf")


@router.get("/{analysis_id}/reports/{report_id}")
async def get_report(analysis_id: str, report_id: str) -> FileResponse:
    path = DocumentStorage().report_path(analysis_id, report_id)
    if not path.exists():
        raise AppError("REPORT_NOT_FOUND", "Отчет не найден", status_code=404)
    return FileResponse(path, media_type="application/pdf", filename=f"digital-mentor-report-{report_id}.pdf")

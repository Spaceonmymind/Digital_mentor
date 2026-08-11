from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Analysis, AnalysisResult, DetailedReport, Document
from app.db.session import async_session_factory
from app.schemas.reports import DetailedReportStatusResponse
from app.services.reports import ReportService
from app.services.storage import DocumentStorage


def detailed_report_status(report: DetailedReport | None, analysis_id: str) -> DetailedReportStatusResponse:
    if report is None:
        return DetailedReportStatusResponse(analysis_id=analysis_id, status="not_started", progress=0)
    return DetailedReportStatusResponse(
        analysis_id=analysis_id,
        report_id=report.report_id,
        status=report.status,
        progress=report.progress,
        report_url=report.report_url,
        error_message=report.error_message,
        created_at=report.created_at,
        started_at=report.started_at,
        completed_at=report.completed_at,
    )


async def get_or_create_detailed_report(session: AsyncSession, analysis_id: str) -> DetailedReport:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
    if analysis.status != "completed":
        raise AppError("ANALYSIS_NOT_COMPLETED", "Быстрый результат еще не сформирован", status_code=409)

    report = (
        await session.execute(select(DetailedReport).where(DetailedReport.analysis_id == analysis_id).limit(1))
    ).scalar_one_or_none()
    if report is None:
        report = DetailedReport(
            analysis_id=analysis_id,
            status="pending",
            progress=5,
            format="pdf",
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
    return report


async def get_detailed_report(session: AsyncSession, analysis_id: str) -> DetailedReport | None:
    return (
        await session.execute(select(DetailedReport).where(DetailedReport.analysis_id == analysis_id).limit(1))
    ).scalar_one_or_none()


async def generate_detailed_report_task(analysis_id: str) -> None:
    async with async_session_factory() as session:
        report = await get_or_create_detailed_report(session, analysis_id)
        if report.status == "completed":
            return
        report.status = "running"
        report.progress = 20
        report.error_message = None
        report.started_at = report.started_at or datetime.now(timezone.utc)
        session.add(report)
        await session.commit()

    try:
        async with async_session_factory() as session:
            report = await get_or_create_detailed_report(session, analysis_id)
            analysis = await session.get(Analysis, analysis_id)
            document = await session.get(Document, analysis.document_id) if analysis else None
            result = (
                await session.execute(select(AnalysisResult).where(AnalysisResult.analysis_id == analysis_id).limit(1))
            ).scalar_one_or_none()
            if analysis is None:
                raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)
            if document is None:
                raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
            if result is None:
                raise AppError("ANALYSIS_RESULT_NOT_FOUND", "Результат анализа не найден", status_code=404)

            report.progress = 55
            session.add(report)
            await session.commit()

            response = ReportService().create_detailed_pdf_report(analysis, document, result, report_id=report.report_id)
            report.status = "completed"
            report.progress = 100
            report.report_url = response.report_url
            report.completed_at = datetime.now(timezone.utc)
            session.add(report)
            await session.commit()
    except Exception as exc:
        async with async_session_factory() as session:
            report = await get_detailed_report(session, analysis_id)
            if report is not None:
                report.status = "failed"
                report.error_message = str(exc)
                report.completed_at = datetime.now(timezone.utc)
                session.add(report)
                await session.commit()


def detailed_report_path(analysis_id: str, report: DetailedReport):
    return DocumentStorage().report_path(analysis_id, report.report_id)

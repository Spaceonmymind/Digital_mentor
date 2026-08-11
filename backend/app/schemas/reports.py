from datetime import datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    report_id: str
    analysis_id: str
    format: str
    report_url: str
    created_at: datetime


class DetailedReportStatusResponse(BaseModel):
    analysis_id: str
    report_id: str | None = None
    status: str
    progress: int
    report_url: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

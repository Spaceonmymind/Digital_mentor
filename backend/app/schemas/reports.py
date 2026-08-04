from datetime import datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    report_id: str
    analysis_id: str
    format: str
    report_url: str
    created_at: datetime

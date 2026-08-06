from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssessmentTaskRun(Base):
    __tablename__ = "assessment_task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    criterion_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodology_criteria.id"), nullable=False)
    indicator_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodology_indicators.id"), nullable=False)
    prompt_template_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_templates.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    llm_call_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("llm_calls.id", use_alter=True))
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

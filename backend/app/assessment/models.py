from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    methodology_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodologies.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    methodology: Mapped["Methodology"] = relationship()
    results: Mapped[list["AssessmentResult"]] = relationship(back_populates="assessment")


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    __table_args__ = (
        UniqueConstraint("assessment_id", "methodology_criterion_id", name="uq_assessment_results_criterion"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    methodology_criterion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("methodology_criteria.id"), nullable=False
    )
    severity: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assessment: Mapped[Assessment] = relationship(back_populates="results")
    methodology_criterion: Mapped["MethodologyCriterion"] = relationship()
    indicator_results: Mapped[list["IndicatorResult"]] = relationship(back_populates="assessment_result")


class IndicatorResult(Base):
    __tablename__ = "assessment_indicator_results"
    __table_args__ = (
        UniqueConstraint("assessment_result_id", "methodology_indicator_id", name="uq_indicator_results_indicator"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_results.id"), nullable=False
    )
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    methodology_indicator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("methodology_indicators.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommendation: Mapped[str | None] = mapped_column(Text)
    recommendations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    prompt_template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prompt_templates.id"))
    prompt_version: Mapped[str | None] = mapped_column(String(128))
    llm_call_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("llm_calls.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assessment_result: Mapped[AssessmentResult] = relationship(back_populates="indicator_results")
    methodology_indicator: Mapped["MethodologyIndicator"] = relationship()

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
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


class AgentTaskRun(Base):
    __tablename__ = "agent_task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    methodology_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodology_agents.id"), nullable=False)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    model_role: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prompt_templates.id"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    llm_call_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("llm_calls.id", use_alter=True))
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentResult(Base):
    __tablename__ = "agent_results"
    __table_args__ = (UniqueConstraint("agent_task_run_id", name="uq_agent_results_task_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    agent_task_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_task_runs.id"), nullable=False)
    methodology_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodology_agents.id"), nullable=False)
    agent_code: Mapped[str] = mapped_column(String(64), nullable=False)
    model_role: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_code: Mapped[str | None] = mapped_column(String(128))
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    llm_call_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("llm_calls.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GateDecision(Base):
    __tablename__ = "assessment_gate_decisions"
    __table_args__ = (UniqueConstraint("assessment_id", "gate_code", name="uq_gate_decision_assessment_gate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    gate_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MentorAnalysisResult(Base):
    __tablename__ = "mentor_analysis_results"
    __table_args__ = (UniqueConstraint("assessment_id", name="uq_mentor_analysis_results_assessment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id"), nullable=False)
    analysis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analyses.id"))
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    methodology_code: Mapped[str] = mapped_column(String(128), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_rub: Mapped[float | None] = mapped_column(Numeric(12, 6))
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

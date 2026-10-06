from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkType(Base):
    __tablename__ = "work_types"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_CONFIGURED")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    methodologies: Mapped[list["Methodology"]] = relationship(back_populates="work_type")


class Methodology(Base):
    __tablename__ = "methodologies"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_methodologies_code_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    work_type_code: Mapped[str | None] = mapped_column(String(64), ForeignKey("work_types.code"), index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    max_score: Mapped[int | None] = mapped_column(Integer)
    applicable_formats: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["pdf", "docx"])
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    work_type: Mapped[WorkType | None] = relationship(back_populates="methodologies")
    criteria: Mapped[list["MethodologyCriterion"]] = relationship(back_populates="methodology")
    prompts: Mapped[list["PromptTemplate"]] = relationship(back_populates="methodology")
    agents: Mapped[list["MethodologyAgent"]] = relationship(back_populates="methodology")


class MethodologyCriterion(Base):
    __tablename__ = "methodology_criteria"
    __table_args__ = (UniqueConstraint("methodology_id", "number", name="uq_methodology_criteria_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    methodology_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodologies.id"), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_score: Mapped[int | None] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[str | None] = mapped_column(String(128))

    methodology: Mapped[Methodology] = relationship(back_populates="criteria")
    indicators: Mapped[list["MethodologyIndicator"]] = relationship(back_populates="criterion")


class MethodologyIndicator(Base):
    __tablename__ = "methodology_indicators"
    __table_args__ = (UniqueConstraint("criterion_id", "order_index", name="uq_methodology_indicators_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    criterion_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodology_criteria.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    expected_result: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[str | None] = mapped_column(String(128))

    criterion: Mapped[MethodologyCriterion] = relationship(back_populates="indicators")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("methodology_id", "stage", "version", name="uq_prompt_templates_stage_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    methodology_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodologies.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str | None] = mapped_column(String(128))

    methodology: Mapped[Methodology] = relationship(back_populates="prompts")


class MethodologyAgent(Base):
    __tablename__ = "methodology_agents"
    __table_args__ = (
        UniqueConstraint("methodology_id", "code", "version", name="uq_methodology_agents_code_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    methodology_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodologies.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    model_role: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prompt_templates.id"))
    input_schema_code: Mapped[str | None] = mapped_column(String(128))
    output_schema_code: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str | None] = mapped_column(String(128))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    methodology: Mapped[Methodology] = relationship(back_populates="agents")
    prompt_template: Mapped[PromptTemplate | None] = relationship()

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Methodology(Base):
    __tablename__ = "methodologies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    criteria: Mapped[list["MethodologyCriterion"]] = relationship(back_populates="methodology")
    prompts: Mapped[list["PromptTemplate"]] = relationship(back_populates="methodology")


class MethodologyCriterion(Base):
    __tablename__ = "methodology_criteria"
    __table_args__ = (UniqueConstraint("methodology_id", "number", name="uq_methodology_criteria_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    methodology_id: Mapped[str] = mapped_column(String(36), ForeignKey("methodologies.id"), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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

    methodology: Mapped[Methodology] = relationship(back_populates="prompts")

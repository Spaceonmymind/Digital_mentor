from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_path: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="document")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(64), nullable=False, default="mentor")
    methodology_id: Mapped[str] = mapped_column(String(128), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="analyses")
    events: Mapped[list["AnalysisEvent"]] = relationship(back_populates="analysis")
    result: Mapped["AnalysisResult | None"] = relationship(back_populates="analysis")


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"), nullable=False)
    step_code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="events")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"), nullable=False, unique=True)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="result")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analyses.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

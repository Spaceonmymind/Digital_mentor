import json
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import Assessment
from app.core.config import settings
from app.db.models import Document
from app.execution.errors import execution_error
from app.methodology.models import Methodology, MethodologyCriterion, MethodologyIndicator


class ExecutionContext(BaseModel):
    assessment_id: str
    document_id: str
    methodology_id: str
    methodology_code: str
    methodology_version: str
    criterion_id: str
    criterion_code: str
    criterion_title: str
    criterion_description: str | None
    indicator_id: str
    indicator_code: str
    indicator_title: str
    indicator_description: str | None
    expected_result: str | None
    document_excerpt: str


class DocumentExcerptBuilder:
    def __init__(self, max_chars: int | None = None, strategy: str | None = None):
        self.max_chars = max_chars or settings.ai_document_max_chars
        self.strategy = strategy or settings.ai_document_excerpt_strategy

    def build(self, document: Document) -> str:
        if not document.extracted_path:
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Извлеченный текст документа не найден", status_code=404)
        path = Path(document.extracted_path)
        if not path.exists():
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Извлеченный текст документа не найден", status_code=404)
        payload = json.loads(path.read_text(encoding="utf-8"))
        full_text = str(payload.get("full_text") or "").strip()
        if not full_text:
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Извлеченный текст документа не найден", status_code=404)
        normalized = "\n".join(line.strip() for line in full_text.splitlines() if line.strip())
        if len(normalized) <= self.max_chars:
            return normalized
        if self.strategy != "head_tail":
            raise execution_error(
                "AI_DOCUMENT_CONTEXT_TOO_LARGE",
                "Документ превышает лимит контекста, стратегия сокращения не поддерживается",
                status_code=413,
                details={"strategy": self.strategy, "max_chars": self.max_chars},
            )
        head_chars = int(self.max_chars * 0.7)
        tail_chars = self.max_chars - head_chars
        return (
            normalized[:head_chars].rstrip()
            + "\n\n[DOCUMENT_TRUNCATED: middle omitted]\n\n"
            + normalized[-tail_chars:].lstrip()
        )


class ExecutionContextBuilder:
    def __init__(self, session: AsyncSession, excerpt_builder: DocumentExcerptBuilder | None = None):
        self.session = session
        self.excerpt_builder = excerpt_builder or DocumentExcerptBuilder()

    async def build(
        self,
        assessment: Assessment,
        methodology: Methodology,
        criterion: MethodologyCriterion,
        indicator: MethodologyIndicator,
    ) -> ExecutionContext:
        document = await self.session.get(Document, assessment.artifact_id)
        if document is None or document.deleted_at is not None:
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Документ не найден", status_code=404)
        excerpt = self.excerpt_builder.build(document)
        return ExecutionContext(
            assessment_id=assessment.id,
            document_id=document.id,
            methodology_id=methodology.id,
            methodology_code=methodology.code,
            methodology_version=methodology.version,
            criterion_id=criterion.id,
            criterion_code=criterion.number,
            criterion_title=criterion.title,
            criterion_description=criterion.description,
            indicator_id=indicator.id,
            indicator_code=str(indicator.order_index),
            indicator_title=indicator.title,
            indicator_description=indicator.description,
            expected_result=indicator.expected_result,
            document_excerpt=excerpt,
        )

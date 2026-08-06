import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Analysis, AnalysisEvent, AnalysisResult
from app.db.session import async_session_factory
from app.schemas.results import (
    AiRiskResult,
    AnalysisResultPayload,
    CriterionResult,
    RecommendationResult,
    RemarkResult,
)
from app.schemas.methodology import AnalysisEvidence, MethodologyReference

logger = logging.getLogger(__name__)


MOCK_STEPS = [
    ("document_received", 10, "Документ получен"),
    ("file_validation", 20, "Проверяю формат и структуру файла"),
    ("text_extraction", 35, "Извлекаю текст документа"),
    ("structure_analysis", 48, "Анализирую структуру работы"),
    ("content_analysis", 60, "Анализирую содержание"),
    ("argumentation_analysis", 72, "Оцениваю аргументацию и логику"),
    ("ai_risk_analysis", 84, "Проверяю признаки генеративного ИИ"),
    ("recommendation_generation", 95, "Формирую рекомендации"),
    ("completed", 100, "Анализ завершен"),
]


class MockAnalysisEngine:
    async def run(
        self,
        analysis_id: str,
        document_id: str,
        methodology_id: str,
        methodology_version: str,
    ) -> AnalysisResultPayload:
        logger.info("analysis_started analysis_id=%s document_id=%s", analysis_id, document_id)
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            analysis.status = "processing"
            analysis.started_at = datetime.now(timezone.utc)
            await session.commit()

        for step_code, progress, message in MOCK_STEPS:
            should_stop = await self._write_step(analysis_id, step_code, "processing", progress, message)
            if should_stop:
                logger.info("analysis_cancelled analysis_id=%s", analysis_id)
                return self._build_result(analysis_id, methodology_id, methodology_version)
            await asyncio.sleep(settings.mock_analysis_step_delay)
            should_stop = await self._write_step(analysis_id, step_code, "completed", progress, message)
            if should_stop:
                logger.info("analysis_cancelled analysis_id=%s", analysis_id)
                return self._build_result(analysis_id, methodology_id, methodology_version)

        result = self._build_result(analysis_id, methodology_id, methodology_version)
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            if analysis.status == "cancelled":
                return result
            session.add(AnalysisResult(analysis_id=analysis_id, result_json=result.model_dump(mode="json")))
            analysis.status = "completed"
            analysis.progress = 100
            analysis.current_step = "completed"
            analysis.completed_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info("analysis_completed analysis_id=%s", analysis_id)
        return result

    async def _write_step(self, analysis_id: str, step_code: str, status: str, progress: int, message: str) -> bool:
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            if analysis.status == "cancelled":
                return True
            analysis.status = "processing"
            analysis.current_step = step_code
            analysis.progress = progress
            session.add(
                AnalysisEvent(
                    analysis_id=analysis_id,
                    step_code=step_code,
                    status=status,
                    progress=progress,
                    message=message,
                )
            )
            await session.commit()
        logger.info(
            "analysis_step analysis_id=%s step=%s status=%s progress=%s",
            analysis_id,
            step_code,
            status,
            progress,
        )
        return False

    def _build_result(self, analysis_id: str, methodology_id: str, methodology_version: str) -> AnalysisResultPayload:
        return AnalysisResultPayload(
            analysis_id=analysis_id,
            overall_score=87,
            verdict="Работа выполнена на хорошем уровне",
            criteria=[
                CriterionResult(code="structure", title="Структура", score=94, explanation="Структура работы логична и читается последовательно."),
                CriterionResult(code="argumentation", title="Аргументация", score=81, explanation="Аргументация есть, но часть тезисов требует более сильных доказательств."),
                CriterionResult(code="coverage", title="Полнота раскрытия", score=84, explanation="Тема раскрыта в целом полно, но методология описана недостаточно подробно."),
                CriterionResult(code="academic_style", title="Академический стиль", score=91, explanation="Стиль выдержан, терминология используется корректно."),
                CriterionResult(code="logic", title="Логика", score=86, explanation="Переходы между разделами понятны, выводы требуют усиления."),
            ],
            strengths=[
                "логичная структура документа",
                "корректное использование терминологии",
                "последовательное изложение материала",
                "наличие практических примеров",
                "хорошо сформулированные выводы",
            ],
            improvements=[
                "расширить описание методологии",
                "добавить критерии оценки",
                "усилить сравнительный анализ",
                "добавить авторские выводы",
                "использовать дополнительные источники",
            ],
            remarks=[
                RemarkResult(
                    id="remark-1",
                    title="Недостаточно раскрыта методология",
                    quote="В разделе «Методы исследования» отсутствует описание критериев оценки.",
                    comment="Раздел описывает общий подход, но не фиксирует измеримые критерии оценки.",
                    recommendation="Добавьте описание выборки, используемых показателей и способа интерпретации результатов.",
                    page=1,
                    section="Методы исследования",
                    severity="warning",
                    priority="Высокий",
                    page_number=1,
                    block_index=0,
                    evidence=[
                        AnalysisEvidence(
                            document_id="demo",
                            page=1,
                            section="Методы исследования",
                            quote="В разделе «Методы исследования» отсутствует описание критериев оценки.",
                            block_index=0,
                        )
                    ],
                ),
                RemarkResult(
                    id="remark-2",
                    title="Нужны авторские выводы",
                    quote="Фрагмент хорошо описывает источники, но слабо показывает позицию автора.",
                    comment="После сравнения решений полезно явно показать самостоятельную позицию автора.",
                    recommendation="Сформулируйте собственный вывод после сравнения решений и объясните, почему он важен для темы.",
                    page=1,
                    section="Выводы",
                    severity="notice",
                    priority="Средний",
                    page_number=1,
                    block_index=1,
                ),
            ],
            ai_risk=AiRiskResult(
                level="medium",
                factors=[
                    "повторяющиеся речевые конструкции",
                    "низкая вариативность синтаксиса",
                    "однотипная аргументация",
                    "недостаточно выраженная авторская позиция",
                ],
                disclaimer="Результат является аналитическим показателем и не может рассматриваться как доказательство использования генеративного ИИ.",
            ),
            recommendations=[
                RecommendationResult(priority="Приоритет 1", title="Добавить подробное описание методологии исследования.", effect="Повысит прозрачность анализа", complexity="Средняя"),
                RecommendationResult(priority="Приоритет 2", title="Расширить сравнительный анализ существующих решений.", effect="Усилит аргументацию", complexity="Средняя"),
                RecommendationResult(priority="Приоритет 3", title="Добавить собственные выводы автора.", effect="Покажет самостоятельность", complexity="Низкая"),
                RecommendationResult(priority="Приоритет 4", title="Подкрепить тезисы дополнительными источниками.", effect="Повысит академичность", complexity="Средняя"),
            ],
            trace=[
                {
                    "engine": "MockAnalysisEngine",
                    "methodology_id": methodology_id,
                    "methodology_version": methodology_version,
                }
            ],
            methodology=MethodologyReference(methodology_id=methodology_id, methodology_version=methodology_version),
            evidence=[],
            extra_blocks={},
        )


def get_analysis_engine() -> MockAnalysisEngine:
    if settings.analysis_engine == "assessment_worker":
        from app.services.assessment_worker_analysis_engine import AssessmentWorkerAnalysisEngine

        return AssessmentWorkerAnalysisEngine()
    return MockAnalysisEngine()

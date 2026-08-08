import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.assessment.models import Assessment, IndicatorResult
from app.assessment.repository import AssessmentRepository
from app.db.models import Analysis, AnalysisEvent, AnalysisResult
from app.db.session import async_session_factory
from app.execution.executor import AssessmentPlanExecutor
from app.methodology.repository import MethodologyRepository
from app.schemas.methodology import MethodologyReference
from app.schemas.results import AiRiskResult, AnalysisResultPayload, CriterionResult


logger = logging.getLogger(__name__)


class AssessmentWorkerAnalysisEngine:
    async def run(
        self,
        analysis_id: str,
        document_id: str,
        methodology_id: str,
        methodology_version: str,
        mode: str = "standard",
    ) -> AnalysisResultPayload:
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            methodology = await MethodologyRepository(session).get_active("UNIVERSAL_DOCUMENT")
            if methodology is None:
                raise RuntimeError("ACTIVE_METHODOLOGY_NOT_FOUND")
            analysis.status = "processing"
            analysis.started_at = datetime.now(timezone.utc)
            analysis.current_step = "assessment_worker"
            analysis.progress = 10
            session.add(
                AnalysisEvent(
                    analysis_id=analysis_id,
                    step_code="assessment_worker",
                    status="processing",
                    progress=10,
                    message="Запущено выполнение worker-задач",
                )
            )
            await session.commit()

            assessment = await AssessmentRepository(session).create_assessment(
                artifact_type="UNIVERSAL_DOCUMENT",
                artifact_id=document_id,
                methodology_id=methodology.id,
                status="created",
            )
            summary = await AssessmentPlanExecutor(session).execute(assessment.id)
            result_payload = await self._build_result_payload(
                session=session,
                analysis_id=analysis_id,
                assessment=assessment,
                methodology_code=methodology.code,
                methodology_version=methodology.version,
            )

            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            session.add(AnalysisResult(analysis_id=analysis_id, result_json=result_payload.model_dump(mode="json")))
            analysis.status = "completed" if summary.tasks_failed == 0 else "failed"
            analysis.progress = 100 if summary.tasks_failed == 0 else 50
            analysis.current_step = "completed" if summary.tasks_failed == 0 else "failed"
            analysis.completed_at = datetime.now(timezone.utc)
            session.add(
                AnalysisEvent(
                    analysis_id=analysis_id,
                    step_code="assessment_worker",
                    status=analysis.status,
                    progress=analysis.progress,
                    message="Worker-задачи завершены",
                )
            )
            await session.commit()
            return result_payload

    async def _build_result_payload(
        self,
        session,
        analysis_id: str,
        assessment: Assessment,
        methodology_code: str,
        methodology_version: str,
    ) -> AnalysisResultPayload:
        results = (
            await session.execute(select(IndicatorResult).where(IndicatorResult.assessment_id == assessment.id))
        ).scalars().all()
        criteria = [
            CriterionResult(
                code=result.methodology_indicator_id,
                title=f"Indicator {index}",
                score=int(result.score or 0),
                explanation=result.summary or result.status,
            )
            for index, result in enumerate(results, start=1)
        ]
        return AnalysisResultPayload(
            analysis_id=analysis_id,
            overall_score=0,
            verdict="Технический результат worker-выполнения без итоговой оценки",
            criteria=criteria,
            strengths=[],
            improvements=[],
            remarks=[],
            ai_risk=AiRiskResult(level="not_evaluated", factors=[], disclaimer="ИИ-риск на этом этапе не рассчитывается."),
            recommendations=[],
            trace=[
                {
                    "engine": "AssessmentWorkerAnalysisEngine",
                    "assessment_id": assessment.id,
                    "methodology_code": methodology_code,
                    "methodology_version": methodology_version,
                }
            ],
            methodology=MethodologyReference(methodology_id=methodology_code, methodology_version=methodology_version),
            evidence=[],
            extra_blocks={"assessment_id": assessment.id},
        )

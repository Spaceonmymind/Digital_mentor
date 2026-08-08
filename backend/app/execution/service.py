from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import IndicatorResult
from app.execution.executor import AssessmentPlanExecutor
from app.execution.schemas import AssessmentExecutionSummary, IndicatorResultListItem


class AssessmentExecutionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.executor = AssessmentPlanExecutor(session)

    async def execute(self, assessment_id: str) -> AssessmentExecutionSummary:
        return await self.executor.execute(assessment_id)

    async def status(self, assessment_id: str) -> AssessmentExecutionSummary:
        return await self.executor.status(assessment_id)

    async def indicator_results(self, assessment_id: str) -> list[IndicatorResultListItem]:
        results = (
            await self.session.execute(
                select(IndicatorResult)
                .where(IndicatorResult.assessment_id == assessment_id)
                .order_by(IndicatorResult.created_at)
            )
        ).scalars().all()
        return [
            IndicatorResultListItem(
                id=result.id,
                assessment_id=result.assessment_id,
                assessment_result_id=result.assessment_result_id,
                methodology_indicator_id=result.methodology_indicator_id,
                status=result.status,
                score=result.score,
                summary=result.summary,
                evidence_json=result.evidence_json,
                recommendations_json=result.recommendations_json,
                confidence=result.confidence,
                prompt_template_id=result.prompt_template_id,
                prompt_version=result.prompt_version,
                llm_call_id=result.llm_call_id,
                created_at=result.created_at.isoformat(),
            )
            for result in results
        ]

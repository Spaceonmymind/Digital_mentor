from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.methodology.models import Methodology, MethodologyCriterion
from app.pipeline.schemas import AssessmentPlan, AssessmentTask


class PlanBuilder:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def build(self, assessment_id: str) -> AssessmentPlan:
        result = await self.session.execute(
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.methodology)
                .selectinload(Methodology.criteria)
                .selectinload(MethodologyCriterion.indicators),
                selectinload(Assessment.methodology).selectinload(Methodology.prompts),
            )
            .limit(1)
        )
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise AppError("ASSESSMENT_NOT_FOUND", "Проверка не найдена", status_code=404)

        prompt_template = self._worker_prompt_template(assessment.methodology)
        tasks: list[AssessmentTask] = []
        for criterion in sorted(assessment.methodology.criteria, key=lambda item: (item.order_index, item.number, item.id)):
            for indicator in sorted(criterion.indicators, key=lambda item: (item.order_index, item.id)):
                tasks.append(
                    AssessmentTask(
                        criterion_id=criterion.id,
                        indicator_id=indicator.id,
                        methodology_id=assessment.methodology_id,
                        prompt_template_id=prompt_template.id,
                        criterion=criterion.title,
                        indicator=indicator.title,
                    )
                )
        return AssessmentPlan(assessment_id=assessment.id, tasks=tasks)

    def _worker_prompt_template(self, methodology: Methodology):
        prompts = [prompt for prompt in methodology.prompts if prompt.stage == "worker"]
        if not prompts:
            raise AppError(
                "WORKER_PROMPT_NOT_FOUND",
                "Шаблон промпта для этапа worker не найден",
                status_code=404,
                details={"methodology_id": methodology.id, "stage": "worker"},
            )
        return sorted(prompts, key=lambda prompt: (prompt.version, prompt.id))[-1]

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import Assessment
from app.core.config import settings
from app.execution.errors import execution_error
from app.execution.models import AssessmentTaskRun
from app.execution.schemas import AssessmentExecutionSummary
from app.execution.worker import WorkerExecutor
from app.pipeline.plan_builder import PlanBuilder


class AssessmentPlanExecutor:
    def __init__(self, session: AsyncSession, worker_executor: WorkerExecutor | None = None):
        self.session = session
        self.worker_executor = worker_executor or WorkerExecutor(session)
        self.plan_builder = PlanBuilder(session)

    async def execute(self, assessment_id: str) -> AssessmentExecutionSummary:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            raise execution_error("ASSESSMENT_NOT_FOUND", "Проверка не найдена", status_code=404)

        plan = await self.plan_builder.build(assessment_id)
        if not plan.tasks:
            raise execution_error("ASSESSMENT_PLAN_EMPTY", "План проверки пуст", status_code=409)

        assessment.status = "running"
        self.session.add(assessment)
        await self.session.commit()

        for task in plan.tasks:
            try:
                await self.worker_executor.execute(task, assessment_id)
            except Exception:
                if settings.ai_execution_stop_on_error:
                    break

        summary = await self.status(assessment_id)
        if summary.tasks_failed:
            assessment.status = "failed"
        elif summary.tasks_completed == summary.tasks_total:
            assessment.status = "completed"
        else:
            assessment.status = "running"
        self.session.add(assessment)
        await self.session.commit()
        return await self.status(assessment_id)

    async def status(self, assessment_id: str) -> AssessmentExecutionSummary:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            raise execution_error("ASSESSMENT_NOT_FOUND", "Проверка не найдена", status_code=404)
        plan = await self.plan_builder.build(assessment_id)
        runs = (
            await self.session.execute(select(AssessmentTaskRun).where(AssessmentTaskRun.assessment_id == assessment_id))
        ).scalars().all()
        completed_ids = {run.indicator_id for run in runs if run.status == "completed"}
        failed = [run for run in runs if run.status == "failed"]
        current_task = None
        for task in plan.tasks:
            if task.indicator_id not in completed_ids:
                current_task = {"criterion": task.criterion, "indicator": task.indicator}
                break
        return AssessmentExecutionSummary(
            assessment_id=assessment_id,
            status=assessment.status,
            tasks_total=len(plan.tasks),
            tasks_completed=len(completed_ids),
            tasks_failed=len(failed),
            current_task=current_task,
        )

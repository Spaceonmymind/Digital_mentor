import hashlib
import json
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import Assessment, AssessmentResult, IndicatorResult
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Document
from app.execution.context import ExecutionContextBuilder
from app.execution.errors import execution_error
from app.execution.models import AssessmentTaskRun
from app.execution.prompt_renderer import PromptRenderer
from app.execution.schemas import WorkerExecutionResult, WorkerIndicatorOutput
from app.llm.client import LLMClient
from app.llm.errors import LLMError
from app.llm.registry import AGGREGATOR, WORKER
from app.llm.schemas import LLMCallTraceCreate
from app.llm.trace_service import LLMTraceService
from app.methodology.models import Methodology, MethodologyCriterion, MethodologyIndicator, PromptTemplate
from app.pipeline.schemas import AssessmentTask


class WorkerExecutor:
    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClient | None = None,
        context_builder: ExecutionContextBuilder | None = None,
        prompt_renderer: PromptRenderer | None = None,
        analysis_id: str | None = None,
    ):
        self.session = session
        self.llm_client = llm_client
        self.analysis_id = analysis_id
        self.context_builder = context_builder or ExecutionContextBuilder(session)
        self.prompt_renderer = prompt_renderer or PromptRenderer()
        self.trace_service = LLMTraceService(session)

    async def execute(self, task: AssessmentTask, assessment_id: str) -> WorkerExecutionResult:
        assessment, methodology, criterion, indicator, prompt_template = await self._load_entities(task, assessment_id)
        idempotency_key = await self._idempotency_key(assessment, methodology, criterion, indicator, prompt_template)
        cached = await self._completed_result(idempotency_key)
        if cached is not None:
            return WorkerExecutionResult(
                task_run_id=cached["task_run"].id,
                indicator_result_id=cached["indicator_result"].id,
                status="completed",
                cache_hit=True,
                llm_call_id=cached["indicator_result"].llm_call_id,
            )

        task_run = await self._start_task_run(task, assessment_id, idempotency_key)
        try:
            context = await self.context_builder.build(assessment, methodology, criterion, indicator)
            system_prompt, user_prompt = self.prompt_renderer.render(
                prompt_template.system_prompt,
                prompt_template.user_template,
                context,
            )
            try:
                llm_result = await self._ask_worker(system_prompt, user_prompt)
            except LLMError as exc:
                llm_call = await self.trace_service.record(
                    LLMCallTraceCreate(
                        requested_model=WORKER,
                        aggregator=AGGREGATOR,
                        temperature=settings.ai_worker_temperature,
                        max_completion_tokens=settings.ai_worker_max_completion_tokens,
                        seed=settings.ai_worker_seed,
                        analysis_id=self.analysis_id,
                        assessment_id=assessment.id,
                        task_run_id=task_run.id,
                        criterion_id=criterion.id,
                        indicator_id=indicator.id,
                        prompt_template_id=prompt_template.id,
                        status="failed",
                    )
                )
                task_run.llm_call_id = llm_call.id
                self.session.add(task_run)
                await self.session.commit()
                raise exc
            output = self._validate_output(llm_result.output)
            output = self._verify_evidence(output, context.document_excerpt)
            llm_call = await self.trace_service.record_result(
                llm_result,
                analysis_id=self.analysis_id,
                assessment_id=assessment.id,
                task_run_id=task_run.id,
                criterion_id=criterion.id,
                indicator_id=indicator.id,
                prompt_template_id=prompt_template.id,
            )
            assessment_result = await self._assessment_result(assessment.id, criterion.id)
            indicator_result = IndicatorResult(
                assessment_id=assessment.id,
                assessment_result_id=assessment_result.id,
                methodology_indicator_id=indicator.id,
                status=output.status,
                score=output.score,
                summary=output.summary,
                evidence=self._legacy_evidence(output),
                evidence_json=[item.model_dump() for item in output.evidence],
                recommendation=self._legacy_recommendation(output),
                recommendations_json=output.recommendations,
                confidence=output.confidence,
                prompt_template_id=prompt_template.id,
                prompt_version=prompt_template.version,
                llm_call_id=llm_call.id,
                idempotency_key=idempotency_key,
            )
            self.session.add(indicator_result)
            task_run.status = "completed"
            task_run.completed_at = datetime.now(timezone.utc)
            task_run.llm_call_id = llm_call.id
            assessment_result.status = "completed"
            assessment_result.summary = assessment_result.summary or "Technical grouping result"
            self.session.add_all([task_run, assessment_result])
            await self.session.commit()
            await self.session.refresh(indicator_result)
            return WorkerExecutionResult(
                task_run_id=task_run.id,
                indicator_result_id=indicator_result.id,
                status="completed",
                cache_hit=False,
                llm_call_id=llm_call.id,
                tokens=llm_result.usage.total_tokens,
                cost_rub=llm_result.usage.cost_rub,
                provider=llm_result.provider,
                latency_ms=llm_result.latency_ms,
            )
        except AppError as exc:
            await self._fail_task_run(task_run, exc.code)
            raise
        except Exception as exc:
            await self._fail_task_run(task_run, "ASSESSMENT_TASK_FAILED")
            raise execution_error("ASSESSMENT_TASK_FAILED", "Не удалось выполнить задачу проверки", status_code=500) from exc

    async def _ask_worker(self, system_prompt: str, user_prompt: str):
        client = self.llm_client or LLMClient()
        try:
            return await client.ask(
                model=WORKER,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=WorkerIndicatorOutput,
                temperature=settings.ai_worker_temperature,
                max_completion_tokens=settings.ai_worker_max_completion_tokens,
                seed=settings.ai_worker_seed,
            )
        except LLMError as exc:
            if exc.code == "LLM_BAD_REQUEST" and settings.ai_worker_seed is not None:
                return await client.ask(
                    model=WORKER,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=WorkerIndicatorOutput,
                    temperature=settings.ai_worker_temperature,
                    max_completion_tokens=settings.ai_worker_max_completion_tokens,
                    seed=None,
                )
            raise

    async def _load_entities(self, task: AssessmentTask, assessment_id: str):
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            raise execution_error("ASSESSMENT_NOT_FOUND", "Проверка не найдена", status_code=404)
        methodology = await self.session.get(Methodology, task.methodology_id)
        criterion = await self.session.get(MethodologyCriterion, task.criterion_id)
        indicator = await self.session.get(MethodologyIndicator, task.indicator_id)
        prompt_template = await self.session.get(PromptTemplate, task.prompt_template_id)
        if methodology is None:
            raise execution_error("METHODOLOGY_NOT_FOUND", "Методология не найдена", status_code=404)
        if criterion is None or indicator is None:
            raise execution_error("ASSESSMENT_TASK_NOT_FOUND", "Задача проверки не найдена", status_code=404)
        if prompt_template is None or prompt_template.stage != "worker":
            raise execution_error("WORKER_PROMPT_NOT_FOUND", "Шаблон промпта worker не найден", status_code=404)
        return assessment, methodology, criterion, indicator, prompt_template

    async def _idempotency_key(
        self,
        assessment: Assessment,
        methodology: Methodology,
        criterion: MethodologyCriterion,
        indicator: MethodologyIndicator,
        prompt_template: PromptTemplate,
    ) -> str:
        document = await self.session.get(Document, assessment.artifact_id)
        if document is None:
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Документ не найден", status_code=404)
        payload = {
            "assessment_id": assessment.id,
            "document_checksum": document.checksum,
            "methodology_version": methodology.version,
            "criterion_id": criterion.id,
            "indicator_id": indicator.id,
            "prompt_version": prompt_template.version,
            "requested_model": WORKER,
            "generation": {
                "temperature": settings.ai_worker_temperature,
                "max_completion_tokens": settings.ai_worker_max_completion_tokens,
                "seed": settings.ai_worker_seed,
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    async def _completed_result(self, idempotency_key: str) -> dict | None:
        task_run = (
            await self.session.execute(
                select(AssessmentTaskRun).where(
                    AssessmentTaskRun.idempotency_key == idempotency_key,
                    AssessmentTaskRun.status == "completed",
                )
            )
        ).scalar_one_or_none()
        if task_run is None:
            return None
        indicator_result = (
            await self.session.execute(
                select(IndicatorResult).where(
                    IndicatorResult.idempotency_key == idempotency_key,
                    IndicatorResult.llm_call_id.is_not(None),
                )
            )
        ).scalar_one_or_none()
        if indicator_result is None:
            return None
        return {"task_run": task_run, "indicator_result": indicator_result}

    async def _start_task_run(self, task: AssessmentTask, assessment_id: str, idempotency_key: str) -> AssessmentTaskRun:
        existing = (
            await self.session.execute(
                select(AssessmentTaskRun)
                .where(AssessmentTaskRun.idempotency_key == idempotency_key)
                .order_by(AssessmentTaskRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        attempt = 1 if existing is None else existing.attempt + 1
        task_run = AssessmentTaskRun(
            assessment_id=assessment_id,
            criterion_id=task.criterion_id,
            indicator_id=task.indicator_id,
            prompt_template_id=task.prompt_template_id,
            status="running",
            attempt=attempt,
            started_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )
        self.session.add(task_run)
        await self.session.commit()
        await self.session.refresh(task_run)
        return task_run

    async def _assessment_result(self, assessment_id: str, criterion_id: str) -> AssessmentResult:
        result = (
            await self.session.execute(
                select(AssessmentResult).where(
                    AssessmentResult.assessment_id == assessment_id,
                    AssessmentResult.methodology_criterion_id == criterion_id,
                )
            )
        ).scalar_one_or_none()
        if result is not None:
            return result
        result = AssessmentResult(
            assessment_id=assessment_id,
            methodology_criterion_id=criterion_id,
            status="running",
            summary="Technical grouping result",
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def _fail_task_run(self, task_run: AssessmentTaskRun, error_code: str) -> None:
        task_run.status = "failed"
        task_run.error_code = error_code
        task_run.completed_at = datetime.now(timezone.utc)
        self.session.add(task_run)
        await self.session.commit()

    def _validate_output(self, output) -> WorkerIndicatorOutput:
        try:
            if isinstance(output, WorkerIndicatorOutput):
                return output
            return WorkerIndicatorOutput.model_validate(output)
        except ValidationError as exc:
            raise execution_error("WORKER_OUTPUT_INVALID", "Worker вернул некорректный результат", status_code=502) from exc

    def _legacy_evidence(self, output: WorkerIndicatorOutput) -> str | None:
        if not output.evidence:
            return None
        return output.evidence[0].explanation

    def _legacy_recommendation(self, output: WorkerIndicatorOutput) -> str | None:
        return output.recommendations[0] if output.recommendations else None

    def _verify_evidence(self, output: WorkerIndicatorOutput, document_text: str) -> WorkerIndicatorOutput:
        evidence = []
        for item in output.evidence:
            if item.quote and item.quote not in document_text:
                item = item.model_copy(
                    update={
                        "quote": None,
                        "explanation": f"{item.explanation} [quote_not_found_in_extracted_text]",
                    }
                )
            evidence.append(item)
        return output.model_copy(update={"evidence": evidence})

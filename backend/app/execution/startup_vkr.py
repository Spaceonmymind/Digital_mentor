import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment, IndicatorResult
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisResult, Document, LLMCall
from app.db.session import async_session_factory
from app.execution.context import DocumentExcerptBuilder
from app.execution.errors import execution_error
from app.execution.executor import AssessmentPlanExecutor
from app.execution.models import AgentResult, AgentTaskRun, GateDecision, MentorAnalysisResult
from app.execution.prompt_renderer import PromptRenderer
from app.execution.schemas import (
    AgentExecutionResult,
    CriticOutput,
    MentorReport,
    MentorAgentTraceItem,
    MentorAnalysisResultPayload,
    MentorCriterionResult,
    TechnicalAssessmentResult,
)
from app.execution.worker import WorkerExecutor
from app.llm.client import LLMClient
from app.llm.registry import AGGREGATOR, CRITIC, FINAL_EXPERT
from app.llm.schemas import LLMCallTraceCreate, LLMResult
from app.llm.trace_service import LLMTraceService
from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, PromptTemplate
from app.methodology.seeds.startup_vkr.data import METHODOLOGY_VERSION as STARTUP_VKR_CURRENT_VERSION
from app.pipeline.schemas import PipelineBuildRequest
from app.pipeline.service import PipelineService
from app.schemas.methodology import AgentTraceItem, AnalysisEvidence, MethodologyReference
from app.schemas.results import AiRiskResult, AnalysisResultPayload, CriterionResult, RecommendationResult, RemarkResult


class StartupVkrAgentFlow:
    def __init__(self, session: AsyncSession, llm_client: LLMClient | None = None):
        self.session = session
        self.llm_client = llm_client
        self.trace_service = LLMTraceService(session)
        self.renderer = PromptRenderer()

    async def execute(self, assessment_id: str, analysis_id: str | None = None) -> MentorAnalysisResultPayload:
        started = time.monotonic()
        assessment = await self._assessment(assessment_id)
        methodology = await self._methodology(assessment.methodology_id)
        if methodology.code != "STARTUP_VKR":
            raise execution_error("METHODOLOGY_NOT_FOUND", "Сценарий поддерживает только STARTUP_VKR", status_code=409)

        await self._check_cost_or_raise(assessment.id, "worker")
        worker_summary = await AssessmentPlanExecutor(
            self.session,
            WorkerExecutor(self.session, llm_client=self.llm_client, analysis_id=analysis_id),
        ).execute(assessment.id)
        if worker_summary.tasks_failed:
            raise execution_error("ASSESSMENT_EXECUTION_FAILED", "Worker stage failed", status_code=500)

        await self._auto_approve_gate(assessment.id, "G1", "Первичный worker-анализ завершен")

        critic_results = []
        for agent in await self._agents(methodology.id, "critic"):
            critic_results.append(await self._execute_critic(assessment, methodology, agent, analysis_id))

        await self._auto_approve_gate(assessment.id, "G4", "Независимая критика завершена")

        final_result = await self._execute_final(assessment, methodology, analysis_id)
        payload = await self._build_mentor_result(
            assessment,
            methodology,
            final_result,
            int((time.monotonic() - started) * 1000),
        )
        assessment.status = "completed"
        self.session.add(assessment)
        await self.session.commit()
        return payload

    async def resume(self, assessment_id: str, analysis_id: str | None = None) -> MentorAnalysisResultPayload:
        return await self.execute(assessment_id, analysis_id=analysis_id)

    async def retry_failed(self, assessment_id: str, analysis_id: str | None = None) -> MentorAnalysisResultPayload:
        return await self.execute(assessment_id, analysis_id=analysis_id)

    async def progress(self, assessment_id: str) -> dict:
        assessment = await self._assessment(assessment_id)
        worker_runs = (
            await self.session.execute(select(func.count()).select_from(IndicatorResult).where(IndicatorResult.assessment_id == assessment_id))
        ).scalar_one()
        critic_runs = (
            await self.session.execute(
                select(func.count()).select_from(AgentTaskRun).where(
                    AgentTaskRun.assessment_id == assessment_id,
                    AgentTaskRun.model_role == "critic",
                    AgentTaskRun.status == "completed",
                )
            )
        ).scalar_one()
        final_runs = (
            await self.session.execute(
                select(func.count()).select_from(AgentTaskRun).where(
                    AgentTaskRun.assessment_id == assessment_id,
                    AgentTaskRun.model_role == "final_expert",
                    AgentTaskRun.status == "completed",
                )
            )
        ).scalar_one()
        steps = [
            {"title": "Подготовка документа", "status": "completed"},
            {"title": "Первичный анализ", "status": "completed" if worker_runs else "running"},
            {"title": "Независимая критика", "status": "completed" if critic_runs else "pending"},
            {"title": "Синтез заключения", "status": "completed" if final_runs else "pending"},
            {"title": "Формирование рекомендаций", "status": "completed" if final_runs else "pending"},
            {"title": "Завершено", "status": "completed" if assessment.status == "completed" else "pending"},
        ]
        return {"assessment_id": assessment_id, "status": assessment.status, "steps": steps}

    async def result(self, assessment_id: str) -> MentorAnalysisResultPayload:
        result = (
            await self.session.execute(
                select(MentorAnalysisResult).where(MentorAnalysisResult.assessment_id == assessment_id).limit(1)
            )
        ).scalar_one_or_none()
        if result is None:
            raise execution_error("ASSESSMENT_RESULT_NOT_FOUND", "Итоговый результат еще не сформирован", status_code=404)
        return MentorAnalysisResultPayload.model_validate(result.result_json)

    async def student_result(self, assessment_id: str) -> dict:
        payload = await self.result(assessment_id)
        if payload.report is None:
            raise execution_error("MENTOR_REPORT_VALIDATION_FAILED", "A-01 не сформировал MentorReport", status_code=500)
        return self._student_report_json(payload.report)

    async def technical_result(self, assessment_id: str) -> TechnicalAssessmentResult:
        payload = await self.result(assessment_id)
        if payload.technical is None:
            raise execution_error("ASSESSMENT_RESULT_NOT_FOUND", "Технический результат не найден", status_code=404)
        return payload.technical

    def _student_report_json(self, report: MentorReport) -> dict:
        payload = report.model_dump(mode="json")
        if not settings.mentor_block_visible_to_student:
            payload.pop("mentor_block", None)
        return payload

    async def current_gate(self, assessment_id: str) -> dict:
        decisions = (
            await self.session.execute(
                select(GateDecision).where(GateDecision.assessment_id == assessment_id).order_by(GateDecision.created_at)
            )
        ).scalars().all()
        if not decisions:
            return {"assessment_id": assessment_id, "current_gate": "G1", "status": "awaiting_human_review"}
        last = decisions[-1]
        return {
            "assessment_id": assessment_id,
            "current_gate": last.gate_code,
            "status": last.status,
            "decision_source": last.decision_source,
            "reason": last.reason,
        }

    async def decide_gate(self, assessment_id: str, gate_code: str, status: str, reason: str | None = None) -> dict:
        decision = (
            await self.session.execute(
                select(GateDecision).where(GateDecision.assessment_id == assessment_id, GateDecision.gate_code == gate_code)
            )
        ).scalar_one_or_none()
        if decision is None:
            decision = GateDecision(assessment_id=assessment_id, gate_code=gate_code)
        decision.status = status
        decision.decision_source = "human"
        decision.reason = reason
        decision.decided_at = datetime.now(timezone.utc)
        self.session.add(decision)
        await self.session.commit()
        return await self.current_gate(assessment_id)

    async def _execute_critic(
        self,
        assessment: Assessment,
        methodology: Methodology,
        agent: MethodologyAgent,
        analysis_id: str | None,
    ) -> AgentExecutionResult:
        prompt = await self.session.get(PromptTemplate, agent.prompt_template_id)
        if prompt is None:
            raise execution_error("CRITIC_PROMPT_NOT_FOUND", "Шаблон промпта critic не найден", status_code=404)
        idempotency_key = await self._agent_idempotency_key(assessment, methodology, agent, prompt, CRITIC)
        cached = await self._cached_agent_result(idempotency_key)
        if cached:
            return AgentExecutionResult(
                task_run_id=cached.agent_task_run_id,
                agent_result_id=cached.id,
                agent_code=agent.code,
                model_role=agent.model_role,
                status="completed",
                cache_hit=True,
                llm_call_id=cached.llm_call_id,
            )
        await self._check_cost_or_raise(assessment.id, "critic")
        task_run = await self._start_agent_run(assessment.id, agent, idempotency_key)
        try:
            document_excerpt = await self._document_excerpt(assessment)
            system, user = self.renderer.render_values(
                prompt.system_prompt,
                prompt.user_template,
                {
                    "agent_code": agent.code,
                    "agent_name": agent.name,
                    "agent_rules": self._agent_rules(agent.code),
                    "document_excerpt": document_excerpt,
                    "worker_results": json.dumps(await self._worker_package(assessment.id), ensure_ascii=False),
                },
                scope="critic",
            )
            llm_result = await self._ask(CRITIC, system, user, CriticOutput, settings.ai_critic_temperature, settings.ai_critic_max_completion_tokens)
            return await self._save_agent_success(assessment.id, agent, task_run, llm_result, idempotency_key, analysis_id)
        except Exception as exc:
            await self._save_agent_failure(task_run, exc)
            raise

    async def _execute_final(self, assessment: Assessment, methodology: Methodology, analysis_id: str | None) -> AgentExecutionResult:
        agents = await self._agents(methodology.id, "final_expert")
        if not agents:
            raise execution_error("FINAL_EXPERT_PROMPT_NOT_FOUND", "Финальный агент не найден", status_code=404)
        agent = agents[0]
        prompt = await self.session.get(PromptTemplate, agent.prompt_template_id)
        if prompt is None:
            raise execution_error("FINAL_EXPERT_PROMPT_NOT_FOUND", "Шаблон промпта final_expert не найден", status_code=404)
        idempotency_key = await self._agent_idempotency_key(assessment, methodology, agent, prompt, FINAL_EXPERT)
        cached = await self._cached_agent_result(idempotency_key)
        if cached:
            return AgentExecutionResult(
                task_run_id=cached.agent_task_run_id,
                agent_result_id=cached.id,
                agent_code=agent.code,
                model_role=agent.model_role,
                status="completed",
                cache_hit=True,
                llm_call_id=cached.llm_call_id,
            )
        await self._check_cost_or_raise(assessment.id, "final_expert")
        task_run = await self._start_agent_run(assessment.id, agent, idempotency_key)
        try:
            system, user = self.renderer.render_values(
                prompt.system_prompt,
                prompt.user_template,
                {
                    "methodology_code": methodology.code,
                    "methodology_version": methodology.version,
                    "result_package": json.dumps(await self._final_package(assessment.id), ensure_ascii=False),
                },
                scope="final",
            )
            llm_result = await self._ask(
                FINAL_EXPERT,
                system,
                user,
                MentorReport,
                settings.ai_final_expert_temperature,
                settings.ai_final_expert_max_completion_tokens,
            )
            return await self._save_agent_success(assessment.id, agent, task_run, llm_result, idempotency_key, analysis_id)
        except Exception as exc:
            await self._save_agent_failure(task_run, exc)
            raise

    async def _ask(self, model: str, system: str, user: str, response_model, temperature: float, max_tokens: int):
        client = self.llm_client or LLMClient()
        return await client.ask(
            model=model,
            system_prompt=system,
            user_prompt=user,
            response_model=response_model,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )

    async def _save_agent_success(
        self,
        assessment_id: str,
        agent: MethodologyAgent,
        task_run: AgentTaskRun,
        llm_result: LLMResult,
        idempotency_key: str,
        analysis_id: str | None,
    ) -> AgentExecutionResult:
        llm_call = await self.trace_service.record_result(
            llm_result,
            analysis_id=analysis_id,
            assessment_id=assessment_id,
            agent_task_run_id=task_run.id,
            methodology_agent_id=agent.id,
            agent_code=agent.code,
            stage_code=agent.stage_code,
            prompt_template_id=agent.prompt_template_id,
        )
        output = llm_result.output.model_dump()
        agent_result = AgentResult(
            assessment_id=assessment_id,
            agent_task_run_id=task_run.id,
            methodology_agent_id=agent.id,
            agent_code=agent.code,
            model_role=agent.model_role,
            output_schema_code=agent.output_schema_code,
            output_json=output,
            summary=output.get("executive_summary") or output.get("verdict"),
            confidence=output.get("confidence"),
            llm_call_id=llm_call.id,
            idempotency_key=idempotency_key,
        )
        task_run.status = "completed"
        task_run.completed_at = datetime.now(timezone.utc)
        task_run.llm_call_id = llm_call.id
        self.session.add_all([task_run, agent_result])
        await self.session.commit()
        await self.session.refresh(agent_result)
        return AgentExecutionResult(
            task_run_id=task_run.id,
            agent_result_id=agent_result.id,
            agent_code=agent.code,
            model_role=agent.model_role,
            status="completed",
            llm_call_id=llm_call.id,
            tokens=llm_result.usage.total_tokens,
            cost_rub=llm_result.usage.cost_rub,
            provider=llm_result.provider,
            latency_ms=llm_result.latency_ms,
        )

    async def _save_agent_failure(self, task_run: AgentTaskRun, exc: Exception) -> None:
        task_run.status = "failed"
        task_run.error_code = getattr(exc, "code", "ASSESSMENT_TASK_FAILED")
        task_run.completed_at = datetime.now(timezone.utc)
        self.session.add(task_run)
        await self.session.commit()

    async def _build_mentor_result(
        self,
        assessment: Assessment,
        methodology: Methodology,
        final_result: AgentExecutionResult,
        processing_time_ms: int,
    ) -> MentorAnalysisResultPayload:
        final_agent_result = await self.session.get(AgentResult, final_result.agent_result_id)
        report = MentorReport.model_validate(final_agent_result.output_json)
        llm_calls = (
            await self.session.execute(select(LLMCall).where(LLMCall.assessment_id == assessment.id))
        ).scalars().all()
        total_tokens = sum(call.total_tokens for call in llm_calls)
        total_cost = sum((call.cost_rub or Decimal("0")) for call in llm_calls)
        worker_package = await self._worker_package(assessment.id)
        agent_results = (
            await self.session.execute(select(AgentResult).where(AgentResult.assessment_id == assessment.id))
        ).scalars().all()
        trace = [
            MentorAgentTraceItem(
                agent_code=result.agent_code,
                agent_version="anti_during_v1_26_impl_v1_10",
                model_role=result.model_role,
                llm_call_id=result.llm_call_id,
                evidence_references=[],
            )
            for result in agent_results
        ]
        criteria = [
            MentorCriterionResult(
                criterion=item["criterion"],
                status=item["status"],
                summary=item["summary"],
                indicators=[item],
                provenance=trace[:1],
            )
            for item in worker_package
        ]
        technical = TechnicalAssessmentResult(
            assessment_id=assessment.id,
            document_id=assessment.artifact_id,
            methodology_code=methodology.code,
            methodology_version=methodology.version,
            anti_during_method_version="1.26",
            anti_during_implementation_version="1.10",
            agent_trace=trace,
            worker_results=worker_package,
            critic_results=[
                {"agent_code": result.agent_code, "output": result.output_json, "llm_call_id": result.llm_call_id}
                for result in agent_results
                if result.model_role == "critic"
            ],
            final_result=report.model_dump(mode="json"),
            evidence_diagnostics=self._evidence_diagnostics(worker_package),
            total_tokens=total_tokens,
            total_cost_rub=total_cost,
            processing_time_ms=processing_time_ms,
        )
        payload = MentorAnalysisResultPayload(
            assessment_id=assessment.id,
            document_id=assessment.artifact_id,
            methodology_code=methodology.code,
            methodology_version=methodology.version,
            status="requires_revision" if not report.veto.is_active else "insufficient_data",
            overall_score=None,
            executive_summary=report.what_this_work_is,
            criteria=criteria,
            strengths=report.what_survived,
            issues=[item.title for item in report.objections],
            contradictions=[item.why for item in report.objections],
            recommendations=[],
            questions_to_author=[report.one_question.question],
            agent_trace=trace,
            total_tokens=total_tokens,
            total_cost_rub=total_cost,
            processing_time_ms=processing_time_ms,
            limitations=[],
            report=report,
            technical=technical,
            spoken_summary=report.spoken_summary,
        )
        stored = (
            await self.session.execute(
                select(MentorAnalysisResult).where(MentorAnalysisResult.assessment_id == assessment.id).limit(1)
            )
        ).scalar_one_or_none()
        if stored is None:
            stored = MentorAnalysisResult(assessment_id=assessment.id, document_id=assessment.artifact_id)
        stored.methodology_code = methodology.code
        stored.methodology_version = methodology.version
        stored.status = payload.status
        stored.result_json = payload.model_dump(mode="json")
        stored.total_tokens = total_tokens
        stored.total_cost_rub = total_cost
        stored.processing_time_ms = processing_time_ms
        self.session.add(stored)
        await self.session.commit()
        return payload

    def _evidence_diagnostics(self, worker_package: list[dict]) -> list[dict]:
        diagnostics = []
        for item in worker_package:
            for evidence in item.get("evidence") or []:
                diagnostics.append(
                    {
                        "indicator_result_id": item.get("indicator_result_id"),
                        "indicator": item.get("indicator"),
                        "evidence_status": "verified" if evidence.get("quote") else "unverified",
                        "section": evidence.get("section"),
                    }
                )
        return diagnostics

    async def _assessment(self, assessment_id: str) -> Assessment:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            raise execution_error("ASSESSMENT_NOT_FOUND", "Проверка не найдена", status_code=404)
        return assessment

    async def _methodology(self, methodology_id: str) -> Methodology:
        methodology = await self.session.get(Methodology, methodology_id)
        if methodology is None:
            raise execution_error("METHODOLOGY_NOT_FOUND", "Методология не найдена", status_code=404)
        return methodology

    async def _agents(self, methodology_id: str, model_role: str) -> list[MethodologyAgent]:
        result = await self.session.execute(
            select(MethodologyAgent)
            .where(
                MethodologyAgent.methodology_id == methodology_id,
                MethodologyAgent.model_role == model_role,
                MethodologyAgent.is_active.is_(True),
            )
            .order_by(MethodologyAgent.execution_order, MethodologyAgent.code)
        )
        return list(result.scalars().all())

    async def _start_agent_run(self, assessment_id: str, agent: MethodologyAgent, idempotency_key: str) -> AgentTaskRun:
        existing = (
            await self.session.execute(
                select(AgentTaskRun)
                .where(AgentTaskRun.idempotency_key == idempotency_key)
                .order_by(AgentTaskRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        task_run = AgentTaskRun(
            assessment_id=assessment_id,
            methodology_agent_id=agent.id,
            stage_code=agent.stage_code,
            agent_code=agent.code,
            model_role=agent.model_role,
            prompt_template_id=agent.prompt_template_id,
            status="running",
            attempt=1 if existing is None else existing.attempt + 1,
            started_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )
        self.session.add(task_run)
        await self.session.commit()
        await self.session.refresh(task_run)
        return task_run

    async def _cached_agent_result(self, idempotency_key: str) -> AgentResult | None:
        return (
            await self.session.execute(
                select(AgentResult).where(AgentResult.idempotency_key == idempotency_key).limit(1)
            )
        ).scalar_one_or_none()

    async def _agent_idempotency_key(
        self,
        assessment: Assessment,
        methodology: Methodology,
        agent: MethodologyAgent,
        prompt: PromptTemplate,
        requested_model: str,
    ) -> str:
        document = await self.session.get(Document, assessment.artifact_id)
        payload = {
            "assessment_id": assessment.id,
            "document_checksum": document.checksum if document else None,
            "methodology_version": methodology.version,
            "agent_id": agent.id,
            "agent_version": agent.version,
            "prompt_version": prompt.version,
            "requested_model": requested_model,
            "worker_results": await self._worker_result_signature(assessment.id),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    async def _worker_result_signature(self, assessment_id: str) -> list:
        results = (
            await self.session.execute(
                select(IndicatorResult).where(IndicatorResult.assessment_id == assessment_id).order_by(IndicatorResult.id)
            )
        ).scalars().all()
        return [{"id": item.id, "llm_call_id": item.llm_call_id, "status": item.status, "score": str(item.score)} for item in results]

    async def _worker_package(self, assessment_id: str) -> list[dict]:
        result = await self.session.execute(
            select(IndicatorResult)
            .where(IndicatorResult.assessment_id == assessment_id)
            .options(selectinload(IndicatorResult.methodology_indicator))
            .order_by(IndicatorResult.created_at)
        )
        rows = result.scalars().all()
        package = []
        for row in rows:
            indicator = row.methodology_indicator
            criterion = await self.session.get(MethodologyCriterion, indicator.criterion_id)
            package.append(
                {
                    "indicator_result_id": row.id,
                    "criterion": criterion.title if criterion else "",
                    "indicator": indicator.title,
                    "status": row.status,
                    "score": str(row.score) if row.score is not None else None,
                    "summary": row.summary,
                    "evidence": row.evidence_json,
                    "recommendations": row.recommendations_json,
                    "confidence": str(row.confidence) if row.confidence is not None else None,
                    "llm_call_id": row.llm_call_id,
                }
            )
        return package

    async def _final_package(self, assessment_id: str) -> dict:
        critics = (
            await self.session.execute(
                select(AgentResult).where(AgentResult.assessment_id == assessment_id, AgentResult.model_role == "critic")
            )
        ).scalars().all()
        return {
            "worker_results": await self._worker_package(assessment_id),
            "critic_results": [
                {
                    "agent_code": result.agent_code,
                    "output": result.output_json,
                    "llm_call_id": result.llm_call_id,
                }
                for result in critics
            ],
            "synthesis_rules": {
                "overall_score": "null because no approved STARTUP_VKR scoring formula is present",
                "do_not_modify_agent_results": True,
            },
        }

    async def _document_excerpt(self, assessment: Assessment) -> str:
        document = await self.session.get(Document, assessment.artifact_id)
        if document is None:
            raise execution_error("AI_DOCUMENT_TEXT_NOT_FOUND", "Документ не найден", status_code=404)
        return DocumentExcerptBuilder().build(document)

    async def _check_cost_or_raise(self, assessment_id: str, next_role: str) -> None:
        calls = (await self.session.execute(select(LLMCall).where(LLMCall.assessment_id == assessment_id))).scalars().all()
        total_cost = sum(float(call.cost_rub or 0) for call in calls)
        if total_cost >= settings.ai_assessment_max_cost_rub:
            raise execution_error("AI_COST_LIMIT_EXCEEDED", "Превышен лимит стоимости AI-анализа", status_code=402)
        counts = {
            "worker": sum(1 for call in calls if call.requested_model and "mistral" in call.requested_model),
            "critic": sum(1 for call in calls if call.requested_model == CRITIC),
            "final_expert": sum(1 for call in calls if call.requested_model == FINAL_EXPERT),
        }
        limits = {
            "worker": settings.ai_max_worker_calls,
            "critic": settings.ai_max_critic_calls,
            "final_expert": settings.ai_max_final_expert_calls,
        }
        if counts[next_role] >= limits[next_role]:
            raise execution_error("AI_COST_LIMIT_EXCEEDED", "Превышен лимит числа AI-вызовов", status_code=402)

    async def _auto_approve_gate(self, assessment_id: str, gate_code: str, reason: str) -> None:
        if not settings.ai_demo_auto_approve_gates:
            assessment = await self._assessment(assessment_id)
            assessment.status = "awaiting_human_review"
            self.session.add(assessment)
            await self.session.commit()
            raise execution_error("AWAITING_HUMAN_REVIEW", "Требуется решение человека", status_code=409)
        decision = (
            await self.session.execute(
                select(GateDecision).where(GateDecision.assessment_id == assessment_id, GateDecision.gate_code == gate_code)
            )
        ).scalar_one_or_none()
        if decision is None:
            decision = GateDecision(assessment_id=assessment_id, gate_code=gate_code)
        decision.status = "approved"
        decision.decision_source = "demo_auto_approve"
        decision.reason = reason
        decision.decided_at = datetime.now(timezone.utc)
        self.session.add(decision)
        await self.session.commit()

    def _agent_rules(self, agent_code: str) -> str:
        rules = {
            "A-15": (
                "Ищи мнимую новизну, эклектику, неподтвержденные утверждения и слишком сильные выводы. "
                "Обязательно выполни девятую проверку ред.1.26: если заявлены приватность, суверенитет, "
                "децентрализация, устойчивость к цензуре или отсутствие центрального доверенного посредника, "
                "найди компонент архитектуры, способный нарушить это свойство. Требуй техническое доказательство "
                "невозможности злоупотребления; 'оператор не будет', 'система доверенная' и 'доступ ограничен политикой' "
                "не являются доказательством."
            ),
            "A-16": "Ищи плохие пути, злоупотребления, отказные сценарии и противоречия конструкции.",
            "A-17": "Проверяй экономику принятия, стимулы, условия да/нет; не предсказывай успех.",
            "A-28": "Проверяй конкретность адресата, его текущую работу и мотив изменить поведение.",
        }
        return rules.get(agent_code, "Проверяй результат worker независимо и не переписывай работу за автора.")


class StartupVkrAnalysisEngine:
    async def run(
        self,
        analysis_id: str,
        document_id: str,
        methodology_id: str,
        methodology_version: str,
    ) -> AnalysisResultPayload:
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            if analysis is None:
                raise RuntimeError("Analysis not found")
            document = await session.get(Document, document_id)
            if document is None:
                raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)

            await self._event(session, analysis, "prepare", 10, "Подготовка документа")
            pipeline = await PipelineService(session).build(
                PipelineBuildRequest(
                    artifact_type="STARTUP_VKR",
                    artifact_id=document.id,
                    filename=document.original_name,
                    metadata={"analysis_id": analysis.id},
                )
            )
            analysis.methodology_id = "STARTUP_VKR"
            analysis.methodology_version = STARTUP_VKR_CURRENT_VERSION
            await self._event(session, analysis, "worker", 30, "Первичный анализ")
            mentor_payload = await StartupVkrAgentFlow(session).execute(pipeline.assessment_id, analysis_id=analysis.id)
            await self._event(session, analysis, "final", 90, "Формирование рекомендаций")
            payload = self._analysis_payload(analysis.id, mentor_payload)
            session.add(AnalysisResult(analysis_id=analysis.id, result_json=payload.model_dump(mode="json")))
            mentor_result = (
                await session.execute(
                    select(MentorAnalysisResult).where(MentorAnalysisResult.assessment_id == mentor_payload.assessment_id).limit(1)
                )
            ).scalar_one_or_none()
            if mentor_result:
                mentor_result.analysis_id = analysis.id
                session.add(mentor_result)
            await session.commit()
            await self._event(session, analysis, "completed", 100, "Завершено")
            return payload

    async def _event(self, session: AsyncSession, analysis: Analysis, step: str, progress: int, message: str) -> None:
        from app.db.models import AnalysisEvent

        analysis.status = "processing" if progress < 100 else "completed"
        analysis.progress = progress
        analysis.current_step = step
        now = datetime.now(timezone.utc)
        analysis.started_at = analysis.started_at or now
        if progress >= 100:
            analysis.completed_at = now
        session.add(analysis)
        session.add(AnalysisEvent(analysis_id=analysis.id, step_code=step, status=analysis.status, progress=progress, message=message))
        await session.commit()

    def _analysis_payload(self, analysis_id: str, mentor: MentorAnalysisResultPayload) -> AnalysisResultPayload:
        report = mentor.report
        if report is None:
            raise execution_error("MENTOR_REPORT_VALIDATION_FAILED", "A-01 не сформировал MentorReport", status_code=500)
        criteria = [
            CriterionResult(
                code=str(index + 1),
                title=item.title,
                score=item.score * 20,
                explanation=f"{item.completed} До следующего уровня: {item.next_level_requirement}",
            )
            for index, item in enumerate(report.stage_assessments)
        ]
        remarks = [
            RemarkResult(
                title=item.title[:120],
                quote="",
                recommendation=item.where_to_move,
                severity="high" if index == 0 else "medium",
            )
            for index, item in enumerate(report.objections)
        ]
        recommendations = [
            RecommendationResult(
                priority="1",
                title=report.one_next_step.step,
                effect=report.one_next_step.check_result,
                complexity="Средняя",
            )
        ]
        return AnalysisResultPayload(
            analysis_id=analysis_id,
            overall_score=0,
            verdict=report.what_this_work_is,
            criteria=criteria,
            strengths=report.what_survived,
            improvements=[item.title for item in report.objections],
            remarks=remarks,
            ai_risk=AiRiskResult(
                level="medium",
                score=None,
                factors=[
                    f"Текущая стадия работы: {report.header.current_stage}",
                    f"Один вопрос: {report.one_question.question}",
                    f"Следующий шаг: {report.one_next_step.step}",
                ],
                disclaimer="Разбор не является подписью человека и не заменяет решение научного руководителя или экспертного совета.",
            ),
            recommendations=recommendations,
            trace=[],
            methodology=MethodologyReference(
                methodology_id=mentor.methodology_code,
                methodology_version=mentor.methodology_version,
            ),
            evidence=[],
            extra_blocks={
                "status": mentor.status,
                "mentor_report": self._student_report_json(report),
                "spoken_summary": report.spoken_summary,
            },
        )

    def _student_report_json(self, report: MentorReport) -> dict:
        payload = report.model_dump(mode="json")
        if not settings.mentor_block_visible_to_student:
            payload.pop("mentor_block", None)
        return payload

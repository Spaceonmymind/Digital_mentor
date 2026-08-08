from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMCall
from app.llm.schemas import LLMCallTraceCreate, LLMResult


class LLMTraceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, trace: LLMCallTraceCreate) -> LLMCall:
        call = LLMCall(
            model=trace.requested_model,
            provider_response_id=trace.provider_response_id,
            requested_model=trace.requested_model,
            actual_model=trace.actual_model,
            aggregator=trace.aggregator,
            provider=trace.provider,
            finish_reason=trace.finish_reason,
            temperature=trace.temperature,
            max_completion_tokens=trace.max_completion_tokens,
            seed=trace.seed,
            analysis_id=trace.analysis_id,
            assessment_id=trace.assessment_id,
            task_run_id=trace.task_run_id,
            agent_task_run_id=trace.agent_task_run_id,
            methodology_agent_id=trace.methodology_agent_id,
            agent_code=trace.agent_code,
            stage_code=trace.stage_code,
            criterion_id=trace.criterion_id,
            indicator_id=trace.indicator_id,
            prompt_template_id=trace.prompt_template_id,
            prompt_tokens=trace.prompt_tokens,
            completion_tokens=trace.completion_tokens,
            total_tokens=trace.total_tokens,
            cached_tokens=trace.cached_tokens,
            reasoning_tokens=trace.reasoning_tokens,
            cost_rub=trace.cost_rub,
            latency_ms=trace.latency_ms,
            status=trace.status,
        )
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def record_result(
        self,
        result: LLMResult,
        analysis_id: str | None = None,
        assessment_id: str | None = None,
        task_run_id: str | None = None,
        agent_task_run_id: str | None = None,
        methodology_agent_id: str | None = None,
        agent_code: str | None = None,
        stage_code: str | None = None,
        criterion_id: str | None = None,
        indicator_id: str | None = None,
        prompt_template_id: str | None = None,
    ) -> LLMCall:
        return await self.record(
            LLMCallTraceCreate(
                provider_response_id=result.provider_response_id,
                requested_model=result.requested_model,
                actual_model=result.actual_model,
                aggregator=result.aggregator,
                provider=result.provider,
                finish_reason=result.finish_reason,
                temperature=result.temperature,
                max_completion_tokens=result.max_completion_tokens,
                seed=result.seed,
                analysis_id=analysis_id,
                assessment_id=assessment_id,
                task_run_id=task_run_id,
                agent_task_run_id=agent_task_run_id,
                methodology_agent_id=methodology_agent_id,
                agent_code=agent_code,
                stage_code=stage_code,
                criterion_id=criterion_id,
                indicator_id=indicator_id,
                prompt_template_id=prompt_template_id,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
                cached_tokens=result.usage.cached_tokens,
                reasoning_tokens=result.usage.reasoning_tokens,
                cost_rub=result.usage.cost_rub,
                latency_ms=result.latency_ms,
                status=result.status,
            )
        )

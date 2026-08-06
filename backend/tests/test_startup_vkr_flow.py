import io
from decimal import Decimal

import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from app.assessment.models import IndicatorResult
from app.db.models import LLMCall
from app.db.session import async_session_factory
from app.execution.models import AgentResult, AgentTaskRun, GateDecision, MentorAnalysisResult
from app.execution.schemas import CriticOutput, FinalExpertOutput, WorkerIndicatorOutput
from app.execution.startup_vkr import StartupVkrAgentFlow
from app.llm.registry import CRITIC, FINAL_EXPERT, WORKER
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import MethodologyAgent, MethodologyCriterion
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.pipeline.schemas import PipelineBuildRequest
from app.pipeline.service import PipelineService
from app.services.extraction import TextExtractionService
from app.services.storage import DocumentStorage


class FakeUpload:
    def __init__(self, content: bytes):
        self.content = content
        self.done = False

    async def read(self, _size: int = -1):
        if self.done:
            return b""
        self.done = True
        return self.content


def docx_bytes(text: str) -> bytes:
    document = DocxDocument()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def seed_document(text: str):
    from app.db.models import Document

    storage = DocumentStorage()
    stored = await storage.save(FakeUpload(docx_bytes(text)), ".docx")
    document = Document(
        original_name="startup-vkr-demo.docx",
        stored_name=stored.stored_name,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=stored.size,
        checksum=stored.checksum,
        storage_path=str(stored.path),
        extraction_status="completed",
        status="uploaded",
    )
    async with async_session_factory() as session:
        session.add(document)
        await session.commit()
        await session.refresh(document)
        extracted_path = storage.extracted_path(document.id)
        TextExtractionService().extract(document.id, stored.path, ".docx", extracted_path)
        document.extracted_path = str(extracted_path)
        await session.commit()
        await session.refresh(document)
        return document


class FakeStartupLLM:
    def __init__(self):
        self.calls = []

    async def ask(self, model, system_prompt, user_prompt, response_model, **kwargs):
        self.calls.append({"model": model, "response_model": response_model.__name__, "user_prompt": user_prompt})
        if response_model is WorkerIndicatorOutput:
            output = WorkerIndicatorOutput(
                status="partially_satisfied",
                score=55,
                summary="Механизм частично описан.",
                strengths=["Есть описание решения"],
                issues=["Есть неподтвержденный вывод"],
                evidence=[{"quote": "цитата которой нет", "page": None, "section": None, "explanation": "Worker сослался на фрагмент"}],
                recommendations=["Уточнить механизм"],
                confidence=0.7,
            )
        elif response_model is CriticOutput:
            output = CriticOutput(
                verdict="revise",
                worker_result_supported=False,
                confirmed_findings=[],
                disputed_findings=[{"worker_finding": "Механизм частично описан", "reason": "Цитата не подтверждена", "evidence": []}],
                missed_issues=["Не проверена экономика принятия"],
                contradictions=[],
                recommended_adjustments=["Попросить автора подтвердить ключевые утверждения"],
                confidence=0.8,
            )
        else:
            output = FinalExpertOutput(
                overall_status="requires_revision",
                overall_score=None,
                executive_summary="Работа требует доработки механизма, доказательств и экономики принятия.",
                strengths=["Есть исходная идея"],
                key_issues=["Недостаточно подтвержденных доказательств"],
                contradictions=[],
                priority_recommendations=[
                    {
                        "priority": 1,
                        "title": "Уточнить механизм",
                        "description": "Показать кто, что, когда и над чем делает.",
                        "expected_effect": "Снимет главный разрыв анализа.",
                        "difficulty": "medium",
                    }
                ],
                criterion_summaries=[
                    {"criterion": "Механизм результата", "summary": "Частично описан.", "status": "requires_revision", "evidence_references": []}
                ],
                questions_to_author=["Как именно решение производит заявленный эффект?"],
                limitations=["Demo auto-approve не является подписью человека."],
                confidence=0.75,
            )
        return LLMResult(
            output=output,
            provider_response_id=f"fake-{len(self.calls)}",
            requested_model=model,
            actual_model=model,
            aggregator="polza.ai",
            provider="fake-provider",
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30, cost_rub=Decimal("0.01")),
            latency_ms=10,
            status="success",
        )


@pytest.mark.asyncio
async def test_startup_vkr_seed_creates_real_methodology_without_demo_plan_items():
    document = await seed_document("ВКР описывает стартап и механизм цифрового сервиса.")
    async with async_session_factory() as session:
        methodology = await ensure_startup_vkr_seed(session)
        criteria = (await session.execute(select(MethodologyCriterion).where(MethodologyCriterion.methodology_id == methodology.id))).scalars().all()
        agents = (await session.execute(select(MethodologyAgent).where(MethodologyAgent.methodology_id == methodology.id))).scalars().all()
        pipeline = await PipelineService(session).build(
            PipelineBuildRequest(artifact_type="STARTUP_VKR", artifact_id=document.id, filename=document.original_name)
        )

    assert methodology.is_demo is False
    assert {criterion.source for criterion in criteria} == {"anti_during_methodology"}
    assert all(criterion.weight is None for criterion in criteria)
    assert len(agents) == 9
    assert pipeline.tasks_count == 7
    assert not any(task.criterion.startswith("Demo") for task in pipeline.tasks)


@pytest.mark.asyncio
async def test_startup_vkr_flow_runs_worker_critic_and_one_final_expert():
    document = await seed_document("Автор предлагает цифровой сервис. Механизм описан частично. Экономика требует проверки.")
    llm = FakeStartupLLM()
    async with async_session_factory() as session:
        await ensure_startup_vkr_seed(session)
        pipeline = await PipelineService(session).build(
            PipelineBuildRequest(artifact_type="STARTUP_VKR", artifact_id=document.id, filename=document.original_name)
        )
        result = await StartupVkrAgentFlow(session, llm_client=llm).execute(pipeline.assessment_id, analysis_id="analysis-1")

    assert result.status == "requires_revision"
    assert result.total_tokens == 360
    assert [call["model"] for call in llm.calls].count(WORKER) == 7
    assert [call["model"] for call in llm.calls].count(CRITIC) == 4
    assert [call["model"] for call in llm.calls].count(FINAL_EXPERT) == 1

    async with async_session_factory() as session:
        indicator_results = (await session.execute(select(IndicatorResult))).scalars().all()
        agent_runs = (await session.execute(select(AgentTaskRun))).scalars().all()
        agent_results = (await session.execute(select(AgentResult))).scalars().all()
        gates = (await session.execute(select(GateDecision))).scalars().all()
        llm_calls = (await session.execute(select(LLMCall))).scalars().all()
        mentor_results = (await session.execute(select(MentorAnalysisResult))).scalars().all()

    assert all((item.evidence_json[0]["quote"] is None) for item in indicator_results)
    assert len(agent_runs) == 5
    assert len(agent_results) == 5
    assert {gate.decision_source for gate in gates} == {"demo_auto_approve"}
    assert {call.requested_model for call in llm_calls} == {WORKER, CRITIC, FINAL_EXPERT}
    assert len(mentor_results) == 1


@pytest.mark.asyncio
async def test_startup_vkr_flow_cache_hit_does_not_call_llm_again():
    document = await seed_document("Повторный запуск должен использовать сохраненные результаты.")
    llm = FakeStartupLLM()
    async with async_session_factory() as session:
        await ensure_startup_vkr_seed(session)
        pipeline = await PipelineService(session).build(
            PipelineBuildRequest(artifact_type="STARTUP_VKR", artifact_id=document.id, filename=document.original_name)
        )
        await StartupVkrAgentFlow(session, llm_client=llm).execute(pipeline.assessment_id, analysis_id="analysis-1")
        await StartupVkrAgentFlow(session, llm_client=llm).execute(pipeline.assessment_id, analysis_id="analysis-1")

    assert len(llm.calls) == 12

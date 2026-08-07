import io
from decimal import Decimal

import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from app.assessment.models import IndicatorResult
from app.db.models import Analysis, AnalysisResult, Document, LLMCall
from app.db.session import async_session_factory
from app.execution.models import AgentResult, AgentTaskRun, GateDecision, MentorAnalysisResult
from app.execution.schemas import CriticOutput, DemoAgentOutput, DemoFinalReport, MentorReport, WorkerIndicatorOutput
from app.execution.startup_vkr import StartupVkrAgentFlow
from app.llm.registry import CRITIC, FINAL_EXPERT, WORKER
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion
from app.methodology.seeds.startup_vkr.data import A15_CHECKS
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.pipeline.schemas import PipelineBuildRequest
from app.pipeline.service import PipelineService
from app.services.extraction import TextExtractionService
from app.services.reports import ReportService
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

    def _mentor_report(self) -> MentorReport:
        return MentorReport(
            header={
                "work_title": "Demo startup VKR",
                "work_type": "ВКР как стартап",
                "analysis_date": "2026-08-07",
                "work_version": None,
                "methodology": "STARTUP_VKR 1.1",
                "current_stage": "S2",
            },
            what_this_work_is="Работа предлагает цифровой сервис, но механизм результата и экономика принятия пока описаны частично.",
            veto={
                "is_active": False,
                "reason": None,
                "why_further_assessment_is_meaningless": None,
                "how_to_remove": None,
            },
            what_survived=["Идея цифрового сервиса сохраняется как предмет дальнейшей проверки."],
            objections=[
                {
                    "title": "Механизм результата пока не доказан",
                    "what_does_not_work": "Из описания не видно, какой компонент производит заявленный эффект.",
                    "why": "Без цепочки действий нельзя отличить работающий механизм от названия технологии.",
                    "where_to_move": "Описать участников, данные, действия и проверяемый результат каждого шага.",
                }
            ],
            one_question={"question": "Какой механизм делает заявленный эффект воспроизводимым?"},
            one_next_step={
                "step": "Постройте схему действий сервиса от входных данных до проверяемого результата.",
                "check_result": "По схеме можно указать, кто выполняет действие и чем подтверждается результат.",
            },
            stage_assessments=[
                {
                    "stage_code": "S1",
                    "title": "Проблема",
                    "score": 3,
                    "completed": "Проблема заявлена и частично описана.",
                    "next_level_requirement": "Показать наблюдаемое событие и масштаб.",
                },
                {
                    "stage_code": "S2",
                    "title": "Противоречие",
                    "score": 2,
                    "completed": "Противоречие намечено.",
                    "next_level_requirement": "Разделить требование результата и ограничение, которое ему мешает.",
                },
            ],
            mentor_block={
                "leading_blind_spot": "Автор смешивает эффект и механизм.",
                "what_changed": "Главный фокус смещен с оформления на проверку конструкции.",
                "what_remains_unresolved": "Не доказана воспроизводимость результата.",
                "mentor_question": "Где в работе можно увидеть механизм, а не обещание?",
                "recommended_intervention": "Попросить автора нарисовать цепочку действий и проверить каждое звено.",
            },
            spoken_summary=(
                "Я закончил разбор. У работы есть исходная идея цифрового сервиса. "
                "Главное противоречие сейчас в том, что механизм результата пока не доказан. "
                "Ответьте сначала на один вопрос: какой механизм делает заявленный эффект воспроизводимым. "
                "Следующий шаг: построить схему действий сервиса от входных данных до проверяемого результата."
            ),
        )

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
        elif response_model is DemoAgentOutput:
            output = DemoAgentOutput(
                summary="Demo-агент нашел ключевой вывод.",
                strengths=["Есть предмет проверки"],
                issues=["Нужно уточнить доказательства"],
                recommendations=["Сжать аргументацию до проверяемой схемы"],
                score=8,
            )
        elif response_model is DemoFinalReport:
            output = DemoFinalReport(
                overall_score=47,
                criteria=[
                    {"name": "Проблема", "score": 8, "comment": "Проблема показана достаточно ясно."},
                    {"name": "Решение", "score": 8, "comment": "Решение понятно, но механизм нужно уточнить."},
                    {"name": "Архитектура", "score": 7, "comment": "Архитектура намечена, отказные сценарии слабые."},
                    {"name": "Экономика", "score": 8, "comment": "Экономика есть, нужны go/no-go пороги."},
                    {"name": "Риски", "score": 7, "comment": "Риски названы, но митигация неполная."},
                    {"name": "Инновационность", "score": 9, "comment": "Идея выглядит новой для выбранного контекста."},
                ],
                strengths=["Есть актуальная проблема", "Есть архитектурная идея", "Есть экономическое обоснование"],
                remarks=["Не хватает отказных сценариев", "Не хватает go/no-go порогов", "Нужно уточнить доказательства"],
                recommendations=["Описать fallback", "Добавить пороги решения", "Сжать механизм в схему"],
                conclusion="Demo-разбор показывает сильную основу и несколько проверяемых направлений доработки.",
                spoken_summary="Demo-анализ завершен: общий балл 47 из 60, главный следующий шаг — уточнить fallback и пороги.",
            )
        else:
            output = self._mentor_report()
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
    assert methodology.version == "1.1"
    assert {criterion.source for criterion in criteria} == {"anti_during_methodology"}
    assert all(criterion.weight is None for criterion in criteria)
    assert len(agents) == 9
    assert pipeline.tasks_count == 7
    assert not any(task.criterion.startswith("Demo") for task in pipeline.tasks)


@pytest.mark.asyncio
async def test_startup_vkr_keeps_old_version_and_uses_new_active_version():
    async with async_session_factory() as session:
        session.add(
            Methodology(
                id="startup-vkr-old-version",
                code="STARTUP_VKR",
                name="ВКР как стартап",
                description="Old reproducible version",
                version="1.0",
                is_active=True,
                is_demo=False,
                source="anti_during_methodology",
            )
        )
        await session.commit()
        methodology = await ensure_startup_vkr_seed(session)

        versions = (
            await session.execute(select(Methodology.version).where(Methodology.code == "STARTUP_VKR").order_by(Methodology.version))
        ).scalars().all()

    assert "1.0" in versions
    assert "1.1" in versions
    assert methodology.version == "1.1"


def test_a15_revision_126_contains_nine_checks():
    assert len(A15_CHECKS) == 9
    assert "заявленное свойство противоречит устройству" in A15_CHECKS


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
    assert result.methodology_version == "1.1"
    assert result.total_tokens == 360
    assert result.report is not None
    assert result.report.header.current_stage == "S2"
    assert len([result.report.one_question.question]) == 1
    assert result.report.one_next_step.step
    assert all(0 <= item.score <= 5 for item in result.report.stage_assessments)
    assert all(item.next_level_requirement for item in result.report.stage_assessments)
    assert result.technical is not None
    report_text = result.report.model_dump_json()
    assert "Worker" not in report_text
    assert "Critic" not in report_text
    assert "quote_not_found" not in report_text
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

    async with async_session_factory() as session:
        public_report = await StartupVkrAgentFlow(session).student_result(mentor_results[0].assessment_id)
        technical = await StartupVkrAgentFlow(session).technical_result(mentor_results[0].assessment_id)

    public_payload = public_report
    assert "mentor_block" not in public_payload
    assert technical.total_tokens == 360


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


@pytest.mark.asyncio
async def test_startup_vkr_demo_flow_keeps_agents_and_returns_short_scored_report():
    document = await seed_document("Резюме проекта. Проблема KYC. Архитектура DID Wallet Verifier. Экономика SAM NPV. Риски отказов.")
    llm = FakeStartupLLM()
    async with async_session_factory() as session:
        await ensure_startup_vkr_seed(session)
        pipeline = await PipelineService(session).build(
            PipelineBuildRequest(artifact_type="STARTUP_VKR", artifact_id=document.id, filename=document.original_name)
        )
        payload, metrics = await StartupVkrAgentFlow(session, llm_client=llm).execute_demo(pipeline.assessment_id, analysis_id="analysis-demo")

    assert payload.overall_score == 47
    assert payload.extra_blocks["mode"] == "demo"
    assert payload.extra_blocks["demo_report"]["overall_score"] == 47
    assert [call["model"] for call in llm.calls].count(WORKER) == 2
    assert [call["model"] for call in llm.calls].count(CRITIC) == 2
    assert [call["model"] for call in llm.calls].count(FINAL_EXPERT) == 1
    assert {call["response_model"] for call in llm.calls} == {"DemoAgentOutput", "DemoFinalReport"}
    assert metrics["mode"] == "demo"
    assert metrics["agent_time_a15"] >= 0


def test_mentor_report_rejects_internal_terms_and_invalid_stage_score():
    valid = {
        "header": {
            "work_title": "Demo",
            "work_type": "ВКР как стартап",
            "analysis_date": "2026-08-07",
            "work_version": None,
            "methodology": "STARTUP_VKR 1.1",
            "current_stage": "S2",
        },
        "what_this_work_is": "Короткое описание работы.",
        "veto": {"is_active": False, "reason": None, "why_further_assessment_is_meaningless": None, "how_to_remove": None},
        "what_survived": ["Есть проверяемый предмет обсуждения."],
        "objections": [
            {
                "title": "Главное возражение",
                "what_does_not_work": "Не показан механизм.",
                "why": "Без механизма невозможно проверить заявленный эффект.",
                "where_to_move": "Описать цепочку действий.",
            }
        ],
        "one_question": {"question": "Как механизм создает результат?"},
        "one_next_step": {"step": "Построить схему механизма.", "check_result": "Каждый шаг имеет вход и выход."},
        "stage_assessments": [
            {
                "stage_code": "S2",
                "title": "Противоречие",
                "score": 5,
                "completed": "Стадия описана.",
                "next_level_requirement": "Проверить воспроизводимость.",
            }
        ],
        "mentor_block": {
            "leading_blind_spot": "Смешаны эффект и механизм.",
            "what_changed": "Фокус уточнен.",
            "what_remains_unresolved": "Нужна проверка механизма.",
            "mentor_question": "Где проверяемая цепочка?",
            "recommended_intervention": "Попросить автора показать схему.",
        },
        "spoken_summary": "Я закончил разбор. Главное противоречие связано с механизмом. Следующий шаг — построить схему.",
    }
    MentorReport.model_validate(valid)
    domain_text = dict(valid)
    domain_text["what_this_work_is"] = "Работа обсуждает токены доступа, стоимость внедрения и экономические издержки как предмет анализа."
    MentorReport.model_validate(domain_text)
    invalid = dict(valid)
    invalid["what_this_work_is"] = "Worker сообщил Assessment ID 12345678-1234-1234-1234-123456789abc."
    with pytest.raises(ValueError):
        MentorReport.model_validate(invalid)
    invalid_score = dict(valid)
    invalid_score["stage_assessments"] = [dict(valid["stage_assessments"][0], score=100)]
    with pytest.raises(ValueError):
        MentorReport.model_validate(invalid_score)


def test_demo_schemas_do_not_emit_unsupported_array_size_keywords():
    agent_schema = DemoAgentOutput.model_json_schema()
    final_schema = DemoFinalReport.model_json_schema()

    schema_text = f"{agent_schema}{final_schema}"

    assert "maxItems" not in schema_text
    assert "minItems" not in schema_text


def test_student_pdf_uses_mentor_report_without_technical_dump():
    report = FakeStartupLLM()._mentor_report().model_dump(mode="json")
    analysis = Analysis(
        id="analysis-without-uuid-like-value",
        document_id="document-1",
        analysis_type="mentor",
        methodology_id="STARTUP_VKR",
        methodology_version="1.1",
        status="completed",
        progress=100,
    )
    document = Document(
        id="document-1",
        original_name="demo.docx",
        stored_name="demo.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=1,
        checksum="checksum",
        storage_path="/tmp/demo.docx",
        extraction_status="completed",
        status="uploaded",
    )
    result = AnalysisResult(analysis_id=analysis.id, result_json={"extra_blocks": {"mentor_report": report}})
    lines = ReportService()._build_lines(analysis, document, result.result_json)
    text = "\n".join(lines)

    assert "ЦИФРОВОЙ МЕНТОР" in text
    assert "Assessment ID" not in text
    assert "Токены" not in text
    assert "Стоимость" not in text
    assert "Worker" not in text
    assert "Critic" not in text

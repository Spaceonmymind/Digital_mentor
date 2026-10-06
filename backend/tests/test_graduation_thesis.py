import asyncio
import json
from collections import Counter

import fitz
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment
from app.db.models import Analysis, Document
from app.db.session import async_session_factory
from app.execution.graduation_thesis import GraduationThesisAgentFlow
from app.execution.rule_preflight import deterministic_document_preflight
from app.execution.rule_schemas import CandidateAgentOutput, CandidateFinalOutput, RuleCheckResult, RuleEvidence
from app.execution.rule_scoring import score_criterion
from app.execution.scientific_article import ScientificArticleAgentFlow
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import Methodology, MethodologyCriterion
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.methodology.seeds.candidate_dissertation import ensure_candidate_dissertation_seed
from app.methodology.seeds.graduation_thesis import ensure_graduation_thesis_seed
from app.methodology.seeds.graduation_thesis import data_v1
from app.methodology.seeds.scientific_article import ensure_scientific_article_seed
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.services.reports import ReportService


@pytest.mark.asyncio
async def test_registration_rules_sources_and_methodology_regressions(client):
    async with async_session_factory() as session:
        gt = await ensure_graduation_thesis_seed(session)
        sa = await ensure_scientific_article_seed(session)
        cd = await ensure_candidate_dissertation_seed(session)
        startup = await ensure_startup_vkr_seed(session)
        loaded = (await session.execute(select(Methodology).where(Methodology.id == gt.id).options(
            selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators), selectinload(Methodology.agents)
        ))).scalar_one()
        sa_loaded = (await session.execute(select(Methodology).where(Methodology.id == sa.id).options(selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators)))).scalar_one()
        cd_loaded = (await session.execute(select(Methodology).where(Methodology.id == cd.id).options(selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators)))).scalar_one()
        startup_loaded = (await session.execute(select(Methodology).where(Methodology.id == startup.id).options(selectinload(Methodology.criteria)))).scalar_one()
        resolved = await MethodologyRegistry(MethodologyRepository(session)).resolve("BACHELOR_SPECIALIST_THESIS")
    rules = [rule for criterion in loaded.criteria for rule in criterion.indicators]
    assert resolved.code == "GRADUATION_THESIS" and resolved.version == "1.0"
    assert loaded.configuration["execution_profile"] == "graduation_thesis"
    assert len(loaded.criteria) == 6 and len(rules) == 42 and loaded.max_score == 60
    assert Counter(r.configuration["normative_strength"] for r in rules) == {"REQUIRED": 30, "CONDITIONAL": 8, "RECOMMENDED": 4}
    assert loaded.configuration["source_type"] == "INTERNAL_METHODOLOGY" and loaded.configuration["is_official"] is False
    assert len(loaded.configuration["limitations"]) == 9
    assert all(r.configuration["source_document"] is None and r.configuration["source_pages"] == [] for r in rules)
    assert "Финансов" not in json.dumps([r.configuration for r in rules], ensure_ascii=False)
    assert len(sa_loaded.criteria) == 6 and sum(len(c.indicators) for c in sa_loaded.criteria) == 37 and sa_loaded.max_score == 60
    assert len(cd_loaded.criteria) == 7 and sum(len(c.indicators) for c in cd_loaded.criteria) == 67 and cd_loaded.max_score == 70
    assert len(startup_loaded.criteria) == 6 and startup_loaded.max_score == 60
    catalog = (await client.get("/api/v1/methodologies")).json()
    item = next(row for row in catalog if row["work_type"] == "BACHELOR_SPECIALIST_THESIS")
    assert item["availability"] == "AVAILABLE" and item["active_version"] == "1.0"


def test_common_preflight_preserves_scientific_article_projection_and_has_thesis_objects():
    payload = {"full_text": "Введение\nСм. [1]\nРисунок 1\nТаблица 1\nПриложение А\nСПИСОК ЛИТЕРАТУРЫ\n1. Источник",
        "paragraphs": [{"paragraph_index": i, "text": text} for i, text in enumerate(
            ["Введение", "См. [1]", "Рисунок 1", "Таблица 1", "Приложение А", "СПИСОК ЛИТЕРАТУРЫ", "1. Источник"])]}
    common = deterministic_document_preflight(payload)
    scientific = ScientificArticleAgentFlow._deterministic_preflight(payload)
    assert scientific["bibliography_found"] == common["bibliography_found"]
    assert scientific["entry_count"] == common["entry_count"]
    assert scientific["missing_entries"] == common["missing_references"]
    assert common["figures"] and common["tables"] and common["applications"]
    assert common["searched_locations"]


def test_work_character_is_internal_non_scoring_and_conditional_is_safe():
    flow = GraduationThesisAgentFlow(None)
    low = flow._infer_work_character({"full_text": "Общий текст выпускной работы"})
    software = flow._infer_work_character({"full_text": "Разработан программный модуль. Код, архитектура и тестирование программного интерфейса."})
    assert low["type"] == "MIXED" and "confidence" in low
    assert software["type"] == "SOFTWARE" and software["confidence"] >= 0.45
    assert "internal_work_character" not in data_v1.CRITERIA[0]
    def scored(status, strength="REQUIRED"):
        return RuleCheckResult(rule_code="GT1.R01", criterion_code="GT1", title="x", status=status, finding="x",
            capability="TEXT", normative_strength=strength)
    assert score_criterion([scored("PASS"), scored("NOT_CHECKED"), scored("NOT_APPLICABLE"), scored("FAIL", "RECOMMENDED")]).score == 10


def test_fake_evidence_unsupported_absence_and_confirmed_absence():
    class Indicator:
        title = "Цель"
        configuration = {"rule_code": "GT1.R03", "source_type": "INTERNAL_METHODOLOGY", "source_document": None,
            "source_section": None, "source_pages": [], "methodology_owner": "Digital Mentor", "methodology_version": "1.0",
            "is_official": False, "authority": None, "capability": "TEXT", "normative_strength": "REQUIRED", "score_weight": 1}
    class Criterion: number, indicators = "GT1", [Indicator()]
    class Method: criteria = [Criterion()]
    flow = GraduationThesisAgentFlow(None)
    cases = [
        ("PASS", [RuleEvidence(quote="выдуманная цитата")], None, [], "NOT_CHECKED"),
        ("FAIL", [], None, [], "NOT_CHECKED"),
        ("FAIL", [], "THEMATIC_SEARCH_NOT_FOUND", ["paragraph:1", "paragraph:2"], "FAIL"),
    ]
    for status, evidence, basis, searched, expected in cases:
        output = CandidateAgentOutput(criterion_code="GT1", summary="x", rule_results=[RuleCheckResult(
            rule_code="GT1.R03", criterion_code="GT1", title="x", status=status, finding="Цель отсутствует.", evidence=evidence,
            verification_basis=basis, searched_context=searched, capability="TEXT", normative_strength="REQUIRED")])
        cleaned = flow._sanitize_output(output, Method(), "реальный текст", "docx", {"GT1"})
        assert cleaned.rule_results[0].status == expected


@pytest.mark.asyncio
async def test_parallel_gt4_gt5_compact_result_reports_and_history(client, tmp_path):
    result_quote = "В тексте представлен как результат автора программный модуль анализа данных."
    class FakeClient:
        def __init__(self): self.active = 0; self.max_active = 0; self.final_prompt = ""
        async def ask(self, model, system_prompt, user_prompt, response_model, **kwargs):
            self.active += 1; self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01); self.active -= 1
            if response_model is CandidateFinalOutput:
                self.final_prompt = user_prompt
                output = CandidateFinalOutput(summary="Предварительный анализ завершён.", represented_result=result_quote)
            else:
                raw = user_prompt.split("Назначенные rules:\n", 1)[1].split("\n\nНедоверенный", 1)[0]
                rules = json.loads(raw); results = []
                for r in rules:
                    if r["rule_code"] == "GT4.R01":
                        results.append(RuleCheckResult(rule_code=r["rule_code"], criterion_code="GT4", title=r["title"], status="PASS",
                            finding=result_quote, evidence=[RuleEvidence(quote=result_quote, block_index=1)], verification_basis="DIRECT_EVIDENCE",
                            capability=r["capability"], normative_strength=r["normative_strength"]))
                    else:
                        results.append(RuleCheckResult(rule_code=r["rule_code"], criterion_code=r["rule_code"].split(".")[0], title=r["title"],
                            status="NOT_CHECKED", finding="Недостаточно контекста.", verification_basis="INSUFFICIENT_CONTEXT",
                            capability=r["capability"], normative_strength=r["normative_strength"]))
                output = CandidateAgentOutput(criterion_code=",".join(sorted({r["rule_code"].split(".")[0] for r in rules})), summary="x", rule_results=results)
            return LLMResult(output=output, requested_model=model, actual_model=model, aggregator="fake", provider="fake",
                temperature=0, max_completion_tokens=kwargs.get("max_completion_tokens"), usage=LLMUsage(), latency_ms=10)
    extracted = tmp_path / "content.json"
    extracted.write_text(json.dumps({"full_text": "Цель работы. Задача разработки. " + result_quote + " Заключение: задача решена.",
        "paragraphs": [{"paragraph_index": 1, "text": result_quote}]}), encoding="utf-8")
    fake = FakeClient()
    async with async_session_factory() as session:
        methodology = await ensure_graduation_thesis_seed(session)
        document = Document(original_name="vkr.docx", stored_name="vkr.docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=1, checksum="x", storage_path=str(tmp_path / "vkr.docx"), extracted_path=str(extracted), extraction_status="completed")
        session.add(document); await session.flush()
        analysis = Analysis(document_id=document.id, analysis_type="mentor", mode="standard", work_type="BACHELOR_SPECIALIST_THESIS",
            methodology_id="GRADUATION_THESIS", methodology_version="1.0", methodology_name="ВКР бакалавра / специалиста",
            methodology_max_score=60, methodology_parameters={}, status="processing", progress=10)
        session.add(analysis); await session.flush()
        assessment = Assessment(artifact_type="BACHELOR_SPECIALIST_THESIS", artifact_id=document.id, methodology_id=methodology.id, status="processing")
        session.add(assessment); await session.commit()
        result = await GraduationThesisAgentFlow(session, fake).execute(assessment, analysis, document)
        payload = result.model_dump(mode="json")
        normal = ReportService()._build_lines(analysis, document, payload)
        detailed = ReportService()._build_detailed_lines(analysis, document, payload)
        await session.commit()
    report = result.extra_blocks["rule_based_report"]
    assert fake.max_active >= 5 and "<document>" not in fake.final_prompt
    assert "represented_result_candidates" in fake.final_prompt and "task_result_conclusion_mapping" in fake.final_prompt
    assert report["represented_result"]["text"].startswith("В тексте представлен как результат автора")
    assert report["internal_work_character"]["type"] in {"SOFTWARE", "MIXED"}
    assert result.extra_blocks["nominal_score_max"] == 60
    assert "Результат, представленный в работе" in normal and "Результат, представленный в работе" in detailed
    assert data_v1.DISCLAIMER in normal and "Нормативные основания rule checks:" not in detailed
    rendered = fitz.open(stream=ReportService()._render_pdf(detailed), filetype="pdf")
    text = "\n".join(page.get_text() for page in rendered); rendered.close()
    assert "Предварительный анализ выпускной" in text and "Результат, представленный" in text
    history = await client.get("/api/v1/analyses/history?methodology=GRADUATION_THESIS")
    item = next(row for row in history.json()["items"] if row["analysis_id"] == analysis.id)
    assert item["methodology_name"] == "ВКР бакалавра / специалиста" and item["methodology_version"] == "1.0"

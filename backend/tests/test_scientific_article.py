import asyncio
import json
from collections import Counter

import pytest
import fitz
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment
from app.db.models import Analysis, Document
from app.db.session import async_session_factory
from app.execution.rule_schemas import CandidateAgentOutput, CandidateFinalOutput, RuleCheckResult, RuleEvidence
from app.execution.rule_scoring import score_criterion
from app.execution.scientific_article import ScientificArticleAgentFlow
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import Methodology, MethodologyCriterion
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.methodology.seeds.candidate_dissertation import ensure_candidate_dissertation_seed
from app.methodology.seeds.scientific_article import ensure_scientific_article_seed
from app.methodology.seeds.scientific_article import data_v1
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.services.reports import ReportService


@pytest.mark.asyncio
async def test_scientific_article_registration_rules_sources_and_regressions(client):
    async with async_session_factory() as session:
        article = await ensure_scientific_article_seed(session)
        candidate = await ensure_candidate_dissertation_seed(session)
        startup = await ensure_startup_vkr_seed(session)
        loaded = (await session.execute(select(Methodology).where(Methodology.id == article.id).options(
            selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators), selectinload(Methodology.agents)
        ))).scalar_one()
        resolved = await MethodologyRegistry(MethodologyRepository(session)).resolve("SCIENTIFIC_ARTICLE")
        candidate_loaded = (await session.execute(select(Methodology).where(Methodology.id == candidate.id).options(
            selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators)
        ))).scalar_one()
    rules = [rule for criterion in loaded.criteria for rule in criterion.indicators]
    strengths = Counter(rule.configuration["normative_strength"] for rule in rules)
    assert resolved.version == "1.0" and resolved.max_score == 60
    assert len(loaded.criteria) == 6 and len(rules) == 37
    assert strengths == {"REQUIRED": 28, "CONDITIONAL": 4, "RECOMMENDED": 4, "OPTIONAL": 1}
    assert loaded.configuration["execution_profile"] == "scientific_article"
    assert loaded.configuration["source_type"] == "INTERNAL_METHODOLOGY"
    assert loaded.configuration["is_official"] is False and loaded.configuration["authority"] is None
    assert len(loaded.configuration["limitations"]) == 7
    assert all(rule.configuration["source_document"] is None and rule.configuration["source_pages"] == [] for rule in rules)
    serialized = json.dumps([rule.configuration for rule in rules], ensure_ascii=False)
    assert "Финансов" not in serialized and "ВАК" not in serialized
    assert {agent.code for agent in loaded.agents} == {"SA-10", "SA-20", "SA-30", "SA-40", "SA-50", "A-01"}
    assert candidate_loaded.max_score == 70 and sum(len(item.indicators) for item in candidate_loaded.criteria) == 67
    assert startup.max_score == 60
    response = await client.get("/api/v1/methodologies")
    item = next(row for row in response.json() if row["work_type"] == "SCIENTIFIC_ARTICLE")
    assert item["availability"] == "AVAILABLE" and item["active_version"] == "1.0"


def test_scoring_and_limitations_are_separate():
    def result(status, strength="REQUIRED"):
        return RuleCheckResult(rule_code="SA1.R01", criterion_code="SA1", title="x", status=status,
            finding="x", capability="TEXT", normative_strength=strength, score_weight=1)
    calculated = score_criterion([result("PASS"), result("PARTIAL"), result("FAIL"), result("NOT_CHECKED"),
                                  result("NOT_APPLICABLE"), result("FAIL", "RECOMMENDED"), result("FAIL", "OPTIONAL")])
    assert calculated.score == 5 and calculated.max_score == 10
    assert not any(limit in json.dumps(data_v1.CRITERIA, ensure_ascii=False) for limit in data_v1.LIMITATIONS)


def test_preflight_does_not_require_imrad_and_verifies_bibliography_absence():
    payload = {"full_text": "Постановка задачи\nПрименён сравнительный подход\nПолучены результаты\nИтог исследования",
               "paragraphs": [{"paragraph_index": i, "text": text} for i, text in enumerate(
                   ["Постановка задачи", "Применён сравнительный подход", "Получены результаты", "Итог исследования"])]}
    preflight = ScientificArticleAgentFlow(None)._deterministic_preflight(payload)
    assert preflight["bibliography_found"] is False
    assert preflight["extraction_chars"] > 0
    assert not any(name in payload["full_text"] for name in ("Methods", "Results", "Discussion", "Conclusion"))


def test_fake_quote_and_unverified_absence_are_not_checked():
    class Indicator:
        title = "Проблема"
        configuration = {"rule_code": "SA1.R01", "source_type": "INTERNAL_METHODOLOGY", "source_document": None,
            "source_section": None, "source_pages": [], "methodology_owner": "Digital Mentor", "methodology_version": "1.0",
            "is_official": False, "authority": None, "capability": "TEXT", "normative_strength": "REQUIRED", "score_weight": 1}
    class Criterion:
        number, indicators = "SA1", [Indicator()]
    class Method:
        criteria = [Criterion()]
    for status, evidence in [("PASS", [RuleEvidence(quote="fake")]), ("FAIL", [])]:
        output = CandidateAgentOutput(criterion_code="SA1", summary="x", rule_results=[RuleCheckResult(
            rule_code="SA1.R01", criterion_code="SA1", title="x", status=status, finding="элемент отсутствует",
            evidence=evidence, capability="TEXT", normative_strength="REQUIRED")])
        cleaned = ScientificArticleAgentFlow(None)._sanitize_output(output, Method(), "реальный текст", "docx", {"SA1"})
        assert cleaned.rule_results[0].status == "NOT_CHECKED"


@pytest.mark.asyncio
async def test_agents_parallel_final_compact_and_rule_report(tmp_path):
    class FakeClient:
        def __init__(self): self.active = 0; self.max_active = 0; self.final_prompt = ""
        async def ask(self, model, system_prompt, user_prompt, response_model, **kwargs):
            self.active += 1; self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01); self.active -= 1
            if response_model is CandidateFinalOutput:
                self.final_prompt = user_prompt
                output = CandidateFinalOutput(summary="Предварительный анализ завершён.")
            else:
                raw = user_prompt.split("Назначенные rules:\n", 1)[1].split("\n\nНедоверенный", 1)[0]
                rules = json.loads(raw)
                output = CandidateAgentOutput(criterion_code=",".join(sorted({r["rule_code"].split(".")[0] for r in rules})), summary="x",
                    rule_results=[RuleCheckResult(rule_code=r["rule_code"], criterion_code=r["rule_code"].split(".")[0],
                        title=r["title"], status="NOT_CHECKED", finding="Недостаточно контекста.", capability=r["capability"],
                        normative_strength=r["normative_strength"], score_weight=r["score_weight"], verification_basis="INSUFFICIENT_CONTEXT") for r in rules])
            return LLMResult(output=output, requested_model=model, actual_model=model, aggregator="fake", provider="fake",
                temperature=0, max_completion_tokens=kwargs.get("max_completion_tokens"), usage=LLMUsage(), latency_ms=10)
    extracted = tmp_path / "content.json"
    extracted.write_text(json.dumps({"full_text": "Цель исследования. Метод. Результат. Вывод.",
        "paragraphs": [{"paragraph_index": 0, "text": "Цель исследования. Метод. Результат. Вывод."}]}), encoding="utf-8")
    fake = FakeClient()
    async with async_session_factory() as session:
        methodology = await ensure_scientific_article_seed(session)
        document = Document(original_name="article.docx", stored_name="article.docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=1, checksum="x", storage_path=str(tmp_path / "article.docx"), extracted_path=str(extracted), extraction_status="completed")
        session.add(document); await session.flush()
        analysis = Analysis(document_id=document.id, analysis_type="mentor", mode="standard", work_type="SCIENTIFIC_ARTICLE",
            methodology_id="SCIENTIFIC_ARTICLE", methodology_version="1.0", methodology_name="Научная статья",
            methodology_max_score=60, methodology_parameters={}, status="processing", progress=10)
        session.add(analysis); await session.flush()
        assessment = Assessment(artifact_type="SCIENTIFIC_ARTICLE", artifact_id=document.id, methodology_id=methodology.id, status="processing")
        session.add(assessment); await session.commit()
        result = await ScientificArticleAgentFlow(session, fake).execute(assessment, analysis, document)
        payload = result.model_dump(mode="json")
        lines = ReportService()._build_lines(analysis, document, payload)
        detailed = ReportService()._build_detailed_lines(analysis, document, payload)
    assert fake.max_active >= 5
    assert "<document>" not in fake.final_prompt and "findings" in fake.final_prompt
    assert result.extra_blocks["nominal_score_max"] == 60
    assert result.extra_blocks["rule_based_report"]["limitations"] == data_v1.LIMITATIONS
    assert "Предварительный анализ научной статьи" in lines and "Методология: Научная статья" in lines
    assert "Нормативные основания rule checks:" not in detailed
    assert "В рамках данного анализа не выполняются:" in lines and "В рамках данного анализа не выполняются:" in detailed
    rendered = fitz.open(stream=ReportService()._render_pdf(detailed), filetype="pdf")
    rendered_text = "\n".join(page.get_text() for page in rendered)
    rendered.close()
    assert "Предварительный анализ научной статьи" in rendered_text
    assert "не является научным рецензированием" in " ".join(rendered_text.split())

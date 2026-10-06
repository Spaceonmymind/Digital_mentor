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
from app.execution.master_dissertation import MasterDissertationAgentFlow
from app.execution.rule_schemas import CandidateAgentOutput, CandidateFinalOutput, RuleCheckResult, RuleEvidence
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import Methodology, MethodologyCriterion
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.methodology.seeds.candidate_dissertation import ensure_candidate_dissertation_seed
from app.methodology.seeds.graduation_thesis import ensure_graduation_thesis_seed
from app.methodology.seeds.master_dissertation import ensure_master_dissertation_seed
from app.methodology.seeds.master_dissertation import data_v1
from app.methodology.seeds.scientific_article import ensure_scientific_article_seed
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.services.reports import ReportService


@pytest.mark.asyncio
async def test_master_registration_rules_sources_and_regressions(client):
    async with async_session_factory() as session:
        master = await ensure_master_dissertation_seed(session)
        graduation = await ensure_graduation_thesis_seed(session)
        scientific = await ensure_scientific_article_seed(session)
        candidate = await ensure_candidate_dissertation_seed(session)
        startup = await ensure_startup_vkr_seed(session)
        async def loaded(item):
            return (await session.execute(select(Methodology).where(Methodology.id == item.id).options(
                selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators), selectinload(Methodology.agents)))).scalar_one()
        master, graduation, scientific, candidate, startup = [await loaded(x) for x in (master, graduation, scientific, candidate, startup)]
        resolved = await MethodologyRegistry(MethodologyRepository(session)).resolve("MASTER_THESIS")
    rules = [r for c in master.criteria for r in c.indicators]
    assert resolved.code == "MASTER_DISSERTATION" and resolved.version == "1.0"
    assert master.configuration["execution_profile"] == "master_dissertation"
    assert len(master.criteria) == 6 and len(rules) == 50 and master.max_score == 60
    assert Counter(r.configuration["normative_strength"] for r in rules) == {"REQUIRED": 34, "CONDITIONAL": 12, "RECOMMENDED": 4}
    assert master.configuration["source_type"] == "INTERNAL_METHODOLOGY" and master.configuration["is_official"] is False
    assert len(master.configuration["limitations"]) == 10
    assert all(r.configuration["source_document"] is None and r.configuration["source_pages"] == [] for r in rules)
    assert next(r for r in rules if r.configuration["rule_code"] == "MD5.R05").configuration["normative_strength"] == "REQUIRED"
    assert next(r for r in rules if r.configuration["rule_code"] == "MD4.R06").configuration["normative_strength"] == "CONDITIONAL"
    assert (len(graduation.criteria), sum(len(c.indicators) for c in graduation.criteria), graduation.max_score) == (6, 42, 60)
    assert (len(scientific.criteria), sum(len(c.indicators) for c in scientific.criteria), scientific.max_score) == (6, 37, 60)
    assert (len(candidate.criteria), sum(len(c.indicators) for c in candidate.criteria), candidate.max_score) == (7, 67, 70)
    assert len(startup.criteria) == 6 and startup.max_score == 60
    item = next(row for row in (await client.get("/api/v1/methodologies")).json() if row["work_type"] == "MASTER_THESIS")
    assert item["availability"] == "AVAILABLE" and item["active_version"] == "1.0"


def test_absent_novelty_is_not_failure_and_work_character_does_not_score():
    class Rule:
        title = "Заявленная научная новизна"
        configuration = {"rule_code": "MD4.R06", "source_type": "INTERNAL_METHODOLOGY", "source_document": None,
            "source_section": None, "source_pages": [], "methodology_owner": "Digital Mentor", "methodology_version": "1.0",
            "is_official": False, "authority": None, "capability": "CROSS_REFERENCE", "normative_strength": "CONDITIONAL", "score_weight": 1}
    flow = MasterDissertationAgentFlow(None)
    flow.work_character = {"type": "MIXED", "confidence": 0.1}
    done, pending = flow._precheck_rules([Rule()], {"full_text": "Цель, метод и результаты исследования.", "paragraphs": []}, "docx")
    assert not pending and done[0].status == "NOT_APPLICABLE"
    assert done[0].verification_basis == "DETERMINISTIC_CHECK"
    assert flow._infer_work_character({"full_text": "Общий текст"})["type"] == "MIXED"


def test_fake_evidence_and_unsupported_absence_are_not_checked_but_verified_absence_is_fail():
    class Indicator:
        title = "Ограничения"
        configuration = {"rule_code": "MD5.R05", "source_type": "INTERNAL_METHODOLOGY", "source_document": None,
            "source_section": None, "source_pages": [], "methodology_owner": "Digital Mentor", "methodology_version": "1.0",
            "is_official": False, "authority": None, "capability": "TEXT", "normative_strength": "REQUIRED", "score_weight": 1}
    class Criterion: number, indicators = "MD5", [Indicator()]
    class Method: criteria = [Criterion()]
    flow = MasterDissertationAgentFlow(None)
    cases = [("PASS", [RuleEvidence(quote="fake")], None, [], "NOT_CHECKED"),
             ("FAIL", [], None, [], "NOT_CHECKED"),
             ("FAIL", [], "THEMATIC_SEARCH_NOT_FOUND", ["section:discussion", "section:conclusion"], "FAIL")]
    for status, evidence, basis, searched, expected in cases:
        output = CandidateAgentOutput(criterion_code="MD5", summary="x", rule_results=[RuleCheckResult(
            rule_code="MD5.R05", criterion_code="MD5", title="x", status=status, finding="Ограничения не найдены.",
            evidence=evidence, verification_basis=basis, searched_context=searched, capability="TEXT", normative_strength="REQUIRED")])
        assert flow._sanitize_output(output, Method(), "реальный текст", "docx", {"MD5"}).rule_results[0].status == expected


@pytest.mark.asyncio
async def test_parallel_compact_contribution_report_and_history(client, tmp_path):
    contribution = "В тексте представлен как самостоятельный вклад автора метод анализа сложных систем."
    class FakeClient:
        def __init__(self): self.active = 0; self.max_active = 0; self.final_prompt = ""
        async def ask(self, model, system_prompt, user_prompt, response_model, **kwargs):
            self.active += 1; self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01); self.active -= 1
            if response_model is CandidateFinalOutput:
                self.final_prompt = user_prompt
                output = CandidateFinalOutput(summary="Предварительный анализ завершён.", represented_result=contribution)
            else:
                raw = user_prompt.split("Назначенные rules:\n", 1)[1].split("\n\nНедоверенный", 1)[0]
                rules = json.loads(raw); results = []
                for r in rules:
                    if r["rule_code"] == "MD4.R01":
                        results.append(RuleCheckResult(rule_code=r["rule_code"], criterion_code="MD4", title=r["title"], status="PASS",
                            finding=contribution, evidence=[RuleEvidence(quote=contribution, block_index=1)], verification_basis="DIRECT_EVIDENCE",
                            capability=r["capability"], normative_strength=r["normative_strength"]))
                    else:
                        results.append(RuleCheckResult(rule_code=r["rule_code"], criterion_code=r["rule_code"].split(".")[0], title=r["title"],
                            status="NOT_CHECKED", finding="Недостаточно контекста.", verification_basis="INSUFFICIENT_CONTEXT",
                            capability=r["capability"], normative_strength=r["normative_strength"]))
                output = CandidateAgentOutput(criterion_code=",".join(sorted({r["rule_code"].split(".")[0] for r in rules})), summary="x", rule_results=results)
            return LLMResult(output=output, requested_model=model, actual_model=model, aggregator="fake", provider="fake",
                temperature=0, max_completion_tokens=kwargs.get("max_completion_tokens"), usage=LLMUsage(), latency_ms=10)
    extracted = tmp_path / "content.json"
    extracted.write_text(json.dumps({"full_text": "Проблема. Цель. Метод. " + contribution + " Результаты интерпретированы. Заключение.",
        "paragraphs": [{"paragraph_index": 1, "text": contribution}]}), encoding="utf-8")
    fake = FakeClient()
    async with async_session_factory() as session:
        methodology = await ensure_master_dissertation_seed(session)
        document = Document(original_name="master.docx", stored_name="master.docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=1, checksum="x", storage_path=str(tmp_path / "master.docx"), extracted_path=str(extracted), extraction_status="completed")
        session.add(document); await session.flush()
        analysis = Analysis(document_id=document.id, analysis_type="mentor", mode="standard", work_type="MASTER_THESIS",
            methodology_id="MASTER_DISSERTATION", methodology_version="1.0", methodology_name="Магистерская диссертация",
            methodology_max_score=60, methodology_parameters={}, status="processing", progress=10)
        session.add(analysis); await session.flush()
        assessment = Assessment(artifact_type="MASTER_THESIS", artifact_id=document.id, methodology_id=methodology.id, status="processing")
        session.add(assessment); await session.commit()
        result = await MasterDissertationAgentFlow(session, fake).execute(assessment, analysis, document)
        payload = result.model_dump(mode="json")
        normal, detailed = ReportService()._build_lines(analysis, document, payload), ReportService()._build_detailed_lines(analysis, document, payload)
    report = result.extra_blocks["rule_based_report"]
    assert fake.max_active >= 5 and "<document>" not in fake.final_prompt
    assert "independent_contribution_candidates" in fake.final_prompt and "research_chain" in fake.final_prompt
    assert report["represented_result"]["title"] == "Самостоятельный вклад, представленный в работе"
    assert report["represented_result"]["text"].startswith("В тексте представлен")
    assert report["internal_work_character"]["type"] in {"RESEARCH", "MIXED"}
    assert result.extra_blocks["nominal_score_max"] == 60
    assert "Самостоятельный вклад, представленный в работе" in normal and data_v1.DISCLAIMER in normal
    assert "Нормативные основания rule checks:" not in detailed
    pdf = fitz.open(stream=ReportService()._render_pdf(detailed), filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf); pdf.close()
    assert "Предварительный анализ магистерской" in text and "Самостоятельный вклад" in text
    history = await client.get("/api/v1/analyses/history?methodology=MASTER_DISSERTATION")
    item = next(row for row in history.json()["items"] if row["analysis_id"] == analysis.id)
    assert item["methodology_name"] == "Магистерская диссертация" and item["methodology_version"] == "1.0"


def test_context_routing_is_limited_and_includes_research_terms():
    flow = MasterDissertationAgentFlow(None)
    flow.work_character = {"type": "RESEARCH", "confidence": 0.8}
    payload = {"full_text": "x" * 50000, "paragraphs": [
        {"paragraph_index": 1, "text": "Исследовательская проблема и гипотеза."},
        {"paragraph_index": 2, "text": "Результаты эксперимента интерпретированы."},
    ]}
    routed = flow._route_context(payload, {"MD1", "MD5"})
    assert "гипотеза" in routed and "эксперимента" in routed and len(routed) <= 14000

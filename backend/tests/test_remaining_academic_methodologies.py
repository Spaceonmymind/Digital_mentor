import asyncio
import json
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment
from app.db.models import Analysis, Document
from app.db.session import async_session_factory
from app.execution.course_paper import CoursePaperAgentFlow, CoursePaperAnalysisEngine
from app.execution.dissertation_abstract import DissertationAbstractAgentFlow, DissertationAbstractAnalysisEngine
from app.execution.doctoral_dissertation import DoctoralDissertationAgentFlow, DoctoralDissertationAnalysisEngine
from app.execution.internship_report import InternshipReportAgentFlow, InternshipReportAnalysisEngine
from app.execution.research_report import ResearchReportAgentFlow, ResearchReportAnalysisEngine
from app.execution.rule_schemas import CandidateAgentOutput, CandidateFinalOutput, RuleCheckResult, RuleEvidence
from app.llm.schemas import LLMResult, LLMUsage
from app.methodology.models import Methodology, MethodologyCriterion, WorkType
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.methodology.seeds.course_paper import ensure_course_paper_seed
from app.methodology.seeds.course_paper import data_v1 as cp
from app.methodology.seeds.dissertation_abstract import ensure_dissertation_abstract_seed
from app.methodology.seeds.dissertation_abstract import data_v1 as da
from app.methodology.seeds.doctoral_dissertation import ensure_doctoral_dissertation_seed
from app.methodology.seeds.doctoral_dissertation import data_v1 as dd
from app.methodology.seeds.internship_report import ensure_internship_report_seed
from app.methodology.seeds.internship_report import data_v1 as ir
from app.methodology.seeds.research_report import ensure_research_report_seed
from app.methodology.seeds.research_report import data_v1 as rr
from app.methodology.seeds.candidate_dissertation import ensure_candidate_dissertation_seed
from app.methodology.seeds.graduation_thesis import ensure_graduation_thesis_seed
from app.methodology.seeds.master_dissertation import ensure_master_dissertation_seed
from app.methodology.seeds.scientific_article import ensure_scientific_article_seed
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.services.methodology_analysis_engine import MethodologyAnalysisEngine
from app.services.reports import ReportService


CASES=[
    (cp,ensure_course_paper_seed,CoursePaperAgentFlow,CoursePaperAnalysisEngine,5,35,{"REQUIRED":29,"CONDITIONAL":4,"RECOMMENDED":2}),
    (ir,ensure_internship_report_seed,InternshipReportAgentFlow,InternshipReportAnalysisEngine,5,32,{"REQUIRED":25,"CONDITIONAL":5,"RECOMMENDED":2}),
    (rr,ensure_research_report_seed,ResearchReportAgentFlow,ResearchReportAnalysisEngine,6,42,{"REQUIRED":30,"CONDITIONAL":8,"RECOMMENDED":4}),
    (dd,ensure_doctoral_dissertation_seed,DoctoralDissertationAgentFlow,DoctoralDissertationAnalysisEngine,7,56,{"REQUIRED":39,"CONDITIONAL":13,"RECOMMENDED":4}),
    (da,ensure_dissertation_abstract_seed,DissertationAbstractAgentFlow,DissertationAbstractAnalysisEngine,6,43,{"REQUIRED":31,"CONDITIONAL":8,"RECOMMENDED":4}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("data,ensure,flow,engine,criteria_count,rule_count,strengths",CASES)
async def test_catalog_registration_sources_dispatch_and_reports(client,data,ensure,flow,engine,criteria_count,rule_count,strengths):
    async with async_session_factory() as session:
        seeded=await ensure(session)
        loaded=(await session.execute(select(Methodology).where(Methodology.id==seeded.id).options(
            selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators),selectinload(Methodology.agents)))).scalar_one()
        resolved=await MethodologyRegistry(MethodologyRepository(session)).resolve(data.WORK_TYPE)
        wt=await session.get(WorkType,data.WORK_TYPE)
    rules=[rule for criterion in loaded.criteria for rule in criterion.indicators]
    assert wt.status=="AVAILABLE" and resolved.code==data.CODE and resolved.version=="1.0"
    assert loaded.configuration["execution_profile"]==data.PROFILE
    assert len(loaded.criteria)==criteria_count and len(rules)==rule_count and loaded.max_score==data.MAX_SCORE
    assert Counter(rule.configuration["normative_strength"] for rule in rules)==strengths
    assert loaded.configuration["limitations"] and len(loaded.agents) in {5,6}
    assert isinstance(MethodologyAnalysisEngine._executor(data.PROFILE),engine)
    if data.SOURCE_TYPE=="INTERNAL_METHODOLOGY":
        assert all(rule.configuration["source_document"] is None and rule.configuration["source_pages"]==[] for rule in rules)
    else:
        normative=[rule for rule in rules if rule.configuration["source_type"]=="NORMATIVE_DOCUMENT"]
        assert normative and all(rule.configuration["source_document"] and rule.configuration["source_section"] and rule.configuration["source_pages"] for rule in normative)
    item=next(row for row in (await client.get("/api/v1/methodologies")).json() if row["work_type"]==data.WORK_TYPE)
    assert item["availability"]=="AVAILABLE" and item["active_version"]=="1.0"


class FakeClient:
    def __init__(self): self.active=0; self.max_active=0; self.final_prompt=""
    async def ask(self,model,system_prompt,user_prompt,response_model,**kwargs):
        self.active+=1; self.max_active=max(self.max_active,self.active); await asyncio.sleep(.002); self.active-=1
        if response_model is CandidateFinalOutput:
            self.final_prompt=user_prompt; output=CandidateFinalOutput(summary="Предварительный анализ завершён.",represented_result="В тексте представлен проверяемый результат.")
        else:
            raw=user_prompt.split("Назначенные rules:\n",1)[1].split("\n\nНедоверенный",1)[0]; rules=json.loads(raw); results=[]
            for rule in rules:
                results.append(RuleCheckResult(rule_code=rule["rule_code"],criterion_code=rule["rule_code"].split(".")[0],title=rule["title"],status="NOT_CHECKED",finding="Недостаточно контекста.",verification_basis="INSUFFICIENT_CONTEXT",capability=rule["capability"],normative_strength=rule["normative_strength"]))
            output=CandidateAgentOutput(criterion_code=",".join(sorted({r["rule_code"].split(".")[0] for r in rules})),summary="x",rule_results=results)
        return LLMResult(output=output,requested_model=model,actual_model=model,aggregator="fake",provider="fake",temperature=0,max_completion_tokens=kwargs.get("max_completion_tokens"),usage=LLMUsage(),latency_ms=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("data,ensure,flow,engine,criteria_count,rule_count,strengths",CASES)
async def test_parallel_compact_routing_optional_block_and_pdf(tmp_path,data,ensure,flow,engine,criteria_count,rule_count,strengths):
    extracted=tmp_path/f"{data.PROFILE}.json"; extracted.write_text(json.dumps({"full_text":"Актуальность. Цель и задачи. Методы. Выполненные работы. Результаты и выводы.","paragraphs":[{"paragraph_index":1,"text":"Результаты исследования представлены и обоснованы."}]}),encoding="utf-8")
    fake=FakeClient()
    async with async_session_factory() as session:
        methodology=await ensure(session)
        document=Document(original_name="fixture.docx",stored_name="fixture.docx",mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",size=1,checksum=data.PROFILE,storage_path=str(tmp_path/"fixture.docx"),extracted_path=str(extracted),extraction_status="completed")
        session.add(document); await session.flush()
        analysis=Analysis(document_id=document.id,analysis_type="mentor",mode="standard",work_type=data.WORK_TYPE,methodology_id=data.CODE,methodology_version="1.0",methodology_name=data.NAME,methodology_max_score=data.MAX_SCORE,methodology_parameters={},status="processing",progress=10)
        session.add(analysis); await session.flush()
        assessment=Assessment(artifact_type=data.WORK_TYPE,artifact_id=document.id,methodology_id=methodology.id,status="processing"); session.add(assessment); await session.commit()
        result=await flow(session,fake).execute(assessment,analysis,document); payload=result.model_dump(mode="json")
    report=result.extra_blocks["rule_based_report"]
    assert fake.max_active>=4 and "<document>" not in fake.final_prompt and len(fake.final_prompt)<50000
    assert report["represented_result"]["title"]==data.RESULT_TITLE
    assert result.extra_blocks["nominal_score_max"]==data.MAX_SCORE
    assert result.extra_blocks["total_score_max"]==0 and result.extra_blocks["coverage"]==0
    normal=ReportService()._build_lines(analysis,document,payload); detailed=ReportService()._build_detailed_lines(analysis,document,payload)
    assert data.REPORT_TITLE in normal and data.DISCLAIMER in normal and data.RESULT_TITLE in normal
    assert ReportService()._render_pdf(normal) and ReportService()._render_pdf(detailed)


def test_cross_methodology_dispatch_is_exact():
    profiles={data.PROFILE:type(MethodologyAnalysisEngine._executor(data.PROFILE)) for data,*_ in CASES}
    assert len(set(profiles.values()))==5
    assert profiles["course_paper"] is not profiles["internship_report"]
    assert profiles["research_report"] is not profiles["doctoral_dissertation"]
    assert profiles["dissertation_abstract"] is not profiles["doctoral_dissertation"]


@pytest.mark.asyncio
async def test_complete_catalog_has_one_active_methodology_and_no_orphans():
    ensures=[ensure_startup_vkr_seed,ensure_course_paper_seed,ensure_graduation_thesis_seed,ensure_master_dissertation_seed,
        ensure_internship_report_seed,ensure_research_report_seed,ensure_scientific_article_seed,
        ensure_candidate_dissertation_seed,ensure_doctoral_dissertation_seed,ensure_dissertation_abstract_seed]
    async with async_session_factory() as session:
        for ensure in ensures: await ensure(session)
        methodologies=(await session.execute(select(Methodology).where(Methodology.is_active.is_(True)).options(
            selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators),selectinload(Methodology.agents)))).scalars().unique().all()
        work_types=(await session.execute(select(WorkType))).scalars().all()
    assert len(methodologies)==10 and len({m.work_type_code for m in methodologies})==10
    assert all(w.status=="AVAILABLE" for w in work_types)
    assert all(m.criteria and m.agents and (m.configuration or {}).get("execution_profile") for m in methodologies)
    assert all(rule.criterion_id for m in methodologies for criterion in m.criteria for rule in criterion.indicators)

import asyncio
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import async_session_factory
from app.execution.models import AgentResult, AgentTaskRun, MentorAnalysisResult
from app.execution.rule_schemas import CandidateAgentOutput, CandidateFinalOutput, RuleCheckResult, RuleEvidence
from app.execution.rule_scoring import score_methodology
from app.llm.client import LLMClient
from app.llm.registry import CRITIC, FINAL_EXPERT, WORKER
from app.llm.trace_service import LLMTraceService
from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate
from app.methodology.seeds.candidate_dissertation.data_v1 import DISCLAIMER
from app.schemas.methodology import AnalysisEvidence, MethodologyReference
from app.schemas.results import AiRiskResult, AnalysisResultPayload, CriterionResult, RecommendationResult, RemarkResult
from app.services.document_context import load_extracted_payload


MODEL_BY_ROLE = {"worker": WORKER, "critic": CRITIC, "final_expert": FINAL_EXPERT}
TEXT_CAPABILITIES = {"TEXT", "STRUCTURE", "CROSS_REFERENCE"}


class CandidateDissertationAgentFlow:
    report_title = "Предварительный анализ кандидатской диссертации"
    report_key = "candidate_dissertation_report"
    disclaimer = DISCLAIMER
    default_recommendation = "Уточнить соответствующий элемент диссертации."

    def _report_extras(self, rule_results, final_output, payload):
        return {}
    def __init__(self, session: AsyncSession, llm_client: LLMClient | None = None):
        self.session = session
        self.llm_client = llm_client

    async def execute(self, assessment: Assessment, analysis: Analysis, document: Document) -> AnalysisResultPayload:
        methodology = await self._methodology(assessment.methodology_id)
        payload = load_extracted_payload(document)
        source_text = payload.get("full_text") or ""
        source_type = "pdf" if document.mime_type == "application/pdf" else "docx"
        agents = sorted((agent for agent in methodology.agents if agent.is_active), key=lambda item: item.execution_order)
        thematic_agents = [agent for agent in agents if agent.stage_code == "analysis"]
        final_agent = next(agent for agent in agents if agent.code == "A-01")
        task_runs = [self._new_run(assessment.id, agent) for agent in thematic_agents]
        self.session.add_all(task_runs)
        await self.session.commit()

        prompts = {prompt.id: prompt for prompt in methodology.prompts}
        calls = [self._call_thematic(agent, methodology, payload, source_type, prompts[agent.prompt_template_id]) for agent in thematic_agents]
        outputs = await asyncio.gather(*calls, return_exceptions=True)
        rule_results: list[RuleCheckResult] = []
        strengths: list[str] = []
        recommendations: list[str] = []
        total_tokens = 0
        total_cost = Decimal("0")
        for agent, task_run, raw in zip(thematic_agents, task_runs, outputs):
            if isinstance(raw, Exception):
                output = self._not_checked_output(agent, methodology, source_type, f"Автоматическая проверка не завершена: {type(raw).__name__}")
                llm_result = None
                task_run.error_code = "CANDIDATE_AGENT_FALLBACK"
            else:
                output, llm_result = raw
            assigned = set((agent.configuration or {}).get("criteria") or [])
            output = self._sanitize_output(output, methodology, source_text, source_type, assigned)
            rule_results.extend(output.rule_results)
            strengths.extend(output.strengths)
            recommendations.extend(output.recommendations)
            llm_call_id = None
            if llm_result is not None:
                trace = await LLMTraceService(self.session).record_result(
                    llm_result, analysis_id=analysis.id, assessment_id=assessment.id,
                    agent_task_run_id=task_run.id, methodology_agent_id=agent.id,
                    agent_code=agent.code, stage_code=agent.stage_code,
                    prompt_template_id=agent.prompt_template_id,
                )
                llm_call_id = trace.id
                total_tokens += llm_result.usage.total_tokens
                total_cost += llm_result.usage.cost_rub or Decimal("0")
            task_run.status = "completed"
            task_run.completed_at = datetime.now(timezone.utc)
            task_run.llm_call_id = llm_call_id
            self.session.add(AgentResult(
                assessment_id=assessment.id, agent_task_run_id=task_run.id,
                methodology_agent_id=agent.id, agent_code=agent.code, model_role=agent.model_role,
                output_schema_code=agent.output_schema_code, output_json=output.model_dump(mode="json"),
                summary=output.summary, confidence=None, llm_call_id=llm_call_id,
                idempotency_key=task_run.idempotency_key,
            ))
        await self.session.commit()

        by_criterion = {criterion.number: [] for criterion in methodology.criteria}
        for item in rule_results:
            by_criterion.setdefault(item.criterion_code, []).append(item)
        scoring = score_methodology(by_criterion)
        compact = self._compact_package(methodology, rule_results, scoring)
        final_run = self._new_run(assessment.id, final_agent)
        self.session.add(final_run)
        await self.session.commit()
        final_output, final_llm = await self._call_final(final_agent, compact, prompts[final_agent.prompt_template_id])
        final_call_id = None
        if final_llm is not None:
            trace = await LLMTraceService(self.session).record_result(
                final_llm, analysis_id=analysis.id, assessment_id=assessment.id,
                agent_task_run_id=final_run.id, methodology_agent_id=final_agent.id,
                agent_code=final_agent.code, stage_code=final_agent.stage_code,
                prompt_template_id=final_agent.prompt_template_id,
            )
            final_call_id = trace.id
            total_tokens += final_llm.usage.total_tokens
            total_cost += final_llm.usage.cost_rub or Decimal("0")
        final_run.status = "completed"
        final_run.completed_at = datetime.now(timezone.utc)
        final_run.llm_call_id = final_call_id
        self.session.add(AgentResult(
            assessment_id=assessment.id, agent_task_run_id=final_run.id,
            methodology_agent_id=final_agent.id, agent_code=final_agent.code, model_role=final_agent.model_role,
            output_schema_code=final_agent.output_schema_code, output_json=final_output.model_dump(mode="json"),
            summary=final_output.summary, confidence=None, llm_call_id=final_call_id,
            idempotency_key=final_run.idempotency_key,
        ))

        criteria = []
        for criterion in sorted(methodology.criteria, key=lambda item: item.order_index):
            calculated = scoring["criteria"][criterion.number]
            criteria.append(CriterionResult(
                code=criterion.number, title=criterion.title, score=calculated.score,
                max_score=calculated.max_score,
                explanation=self._criterion_summary(criterion.number, rule_results),
            ))
        evidence = [
            AnalysisEvidence(document_id=document.id, page=e.page, section=e.section, quote=e.quote, block_index=e.block_index)
            for rule_result in rule_results for e in rule_result.evidence if e.quote
        ]
        failed = [item for item in rule_results if item.status in {"FAIL", "PARTIAL"} and item.normative_strength in {"REQUIRED", "CONDITIONAL"}]
        not_checked = [item for item in rule_results if item.status == "NOT_CHECKED"]
        checked = [item for item in rule_results if item.status in {"PASS", "PARTIAL", "FAIL"}]
        report = {
            "title": self.report_title,
            "methodology_name": methodology.name,
            "methodology_version": methodology.version,
            "disclaimer": self.disclaimer,
            "nominal_max_score": scoring["nominal_max_score"],
            "evaluated_max_score": scoring["evaluated_max_score"],
            "coverage": scoring["coverage"],
            "criterion_results": [
                {"code": item.code, "title": item.title, "score": item.score, "max_score": item.max_score, "status": scoring["criteria"][item.code].status}
                for item in criteria
            ],
            "rule_checks": [item.model_dump(mode="json") for item in rule_results],
            "structure_checks": [item.model_dump(mode="json") for item in rule_results if item.criterion_code == "CD1"],
            "checked_capabilities": sorted({item.capability for item in checked}),
            "not_checked": [item.model_dump(mode="json") for item in not_checked],
            "limitations": list((methodology.configuration or {}).get("limitations") or []),
            "source_type": (methodology.configuration or {}).get("source_type"),
            **self._report_extras(rule_results, final_output, payload),
        }
        result = AnalysisResultPayload(
            analysis_id=analysis.id,
            overall_score=scoring["overall_score"],
            verdict=final_output.summary,
            criteria=criteria,
            strengths=(final_output.strengths or strengths)[:8],
            improvements=[item.finding for item in failed[:8]],
            remarks=[
                RemarkResult(
                    id=item.rule_code, title=item.title,
                    quote=item.evidence[0].quote if item.evidence else "",
                    recommendation=item.recommendation or self.default_recommendation,
                    page=item.evidence[0].page if item.evidence else None,
                    section=item.evidence[0].section if item.evidence else None,
                    severity="medium" if item.status == "PARTIAL" else "high",
                    evidence=[AnalysisEvidence(document_id=document.id, page=e.page, section=e.section, quote=e.quote, block_index=e.block_index) for e in item.evidence],
                ) for item in failed[:10]
            ],
            ai_risk=AiRiskResult(level="preliminary", factors=["Автоматизированная предварительная проверка"], disclaimer=self.disclaimer),
            recommendations=[RecommendationResult(priority=str(i + 1), title=value, effect="Устранение замечания методологии", complexity="medium") for i, value in enumerate((final_output.recommendations or recommendations)[:8])],
            methodology=MethodologyReference(methodology_id=methodology.code, methodology_version=methodology.version),
            evidence=evidence,
            extra_blocks={
                self.report_key: report,
                "rule_based_report": report,
                "total_score_max": scoring["evaluated_max_score"],
                "nominal_score_max": scoring["nominal_max_score"],
                "coverage": scoring["coverage"],
                "assessment_id": assessment.id,
                "total_tokens": total_tokens,
                "total_cost_rub": str(total_cost),
                "limitations": [item.finding for item in not_checked],
            },
        )
        self.session.add(MentorAnalysisResult(
            assessment_id=assessment.id, analysis_id=analysis.id, document_id=document.id,
            methodology_code=methodology.code, methodology_version=methodology.version,
            status="completed", result_json=result.model_dump(mode="json"),
            total_tokens=total_tokens, total_cost_rub=total_cost, processing_time_ms=0,
        ))
        await self.session.commit()
        return result

    async def _methodology(self, methodology_id: str) -> Methodology:
        result = await self.session.execute(
            select(Methodology).where(Methodology.id == methodology_id).options(
                selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators),
                selectinload(Methodology.agents), selectinload(Methodology.prompts),
            )
        )
        return result.scalar_one()

    def _new_run(self, assessment_id: str, agent: MethodologyAgent) -> AgentTaskRun:
        key = sha256(f"{assessment_id}:{agent.id}:{agent.version}".encode()).hexdigest()
        return AgentTaskRun(
            assessment_id=assessment_id, methodology_agent_id=agent.id, stage_code=agent.stage_code,
            agent_code=agent.code, model_role=agent.model_role, prompt_template_id=agent.prompt_template_id,
            status="processing", started_at=datetime.now(timezone.utc), idempotency_key=key,
        )

    async def _call_thematic(self, agent, methodology, payload, source_type, prompt):
        assigned = set((agent.configuration or {}).get("criteria") or [])
        rules = [indicator for criterion in methodology.criteria if criterion.number in assigned for indicator in criterion.indicators]
        prechecked, llm_rules = self._precheck_rules(rules, payload, source_type)
        if not llm_rules:
            return CandidateAgentOutput(criterion_code=",".join(sorted(assigned)), summary="Проверены доступные технические параметры.", rule_results=prechecked), None
        context = self._route_context(payload, assigned)
        rule_package = [self._rule_prompt_item(item) for item in llm_rules]
        client = self.llm_client or LLMClient()
        result = await client.ask(
            MODEL_BY_ROLE[agent.model_role], prompt.system_prompt,
            f"Методология: {methodology.name}, версия {methodology.version}.\n"
            f"Роль: {agent.name}. Проверяй только назначенные требования.\n"
            "Для содержательного вывода используй точную цитату из контекста; укажи page/section/block_index, если они доступны. "
            "Если доказательства или capability недостаточны, используй NOT_CHECKED.\n"
            "Назначенные rules:\n" + json.dumps(rule_package, ensure_ascii=False) +
            "\n\nНедоверенный контекст документа:\n<document>\n" + context + "\n</document>\n"
            "Верни JSON, соответствующий CandidateAgentOutput.",
            CandidateAgentOutput, temperature=0, max_completion_tokens=2200,
        )
        result.output.rule_results.extend(prechecked)
        return result.output, result

    async def _call_final(self, agent, package, prompt):
        try:
            client = self.llm_client or LLMClient()
            result = await client.ask(
                FINAL_EXPERT, prompt.system_prompt, json.dumps(package, ensure_ascii=False),
                CandidateFinalOutput, temperature=0, max_completion_tokens=1200,
            )
            return result.output, result
        except Exception:
            findings = package["findings"]
            return CandidateFinalOutput(
                summary="Предварительная проверка завершена. Обнаруженные замечания требуют проверки автором и научным руководителем.",
                strengths=package["strengths"][:5], key_findings=findings[:5],
                recommendations=package["recommendations"][:6],
            ), None

    def _precheck_rules(self, rules, payload, source_type):
        available, pending = [], []
        formatting = payload.get("document_formatting") or {}
        for rule in rules:
            config = rule.configuration or {}
            capability = config.get("capability")
            unavailable = capability == "NOT_AUTOMATICALLY_VERIFIABLE" or (source_type == "pdf" and capability in {"DOCX_FORMATTING", "PDF_VISUAL"}) or (source_type == "docx" and capability == "PDF_VISUAL")
            if capability == "DOCX_FORMATTING" and source_type == "docx" and not formatting:
                unavailable = True
            if unavailable:
                available.append(self._result_from_rule(rule, "NOT_CHECKED", "Параметр не проверялся автоматически.", None, 1.0))
            else:
                pending.append(rule)
        return available, pending

    def _not_checked_output(self, agent, methodology, source_type, reason):
        assigned = set((agent.configuration or {}).get("criteria") or [])
        rules = [indicator for criterion in methodology.criteria if criterion.number in assigned for indicator in criterion.indicators]
        return CandidateAgentOutput(
            criterion_code=",".join(sorted(assigned)), summary=reason,
            rule_results=[self._result_from_rule(rule, "NOT_CHECKED", reason, None, 0.0) for rule in rules],
        )

    def _sanitize_output(self, output, methodology, source_text, source_type, assigned_criteria=None):
        assigned_criteria = assigned_criteria or set((output.criterion_code or "").split(","))
        known = {
            indicator.configuration.get("rule_code"): indicator
            for criterion in methodology.criteria if criterion.number in assigned_criteria
            for indicator in criterion.indicators
        }
        sanitized = []
        seen = set()
        for item in output.rule_results:
            rule = known.get(item.rule_code)
            if rule is None or item.rule_code in seen:
                continue
            seen.add(item.rule_code)
            config = rule.configuration or {}
            evidence = [e for e in item.evidence if not e.quote or self._quote_exists(e.quote, source_text)]
            status = item.status
            if item.evidence and not evidence and status == "PASS":
                status = "NOT_CHECKED"
            if config["capability"] in TEXT_CAPABILITIES and status in {"PASS", "PARTIAL", "FAIL"} and not evidence:
                status = "NOT_CHECKED"
            sanitized.append(item.model_copy(update={
                "criterion_code": item.rule_code.split(".")[0], "title": rule.title,
                "source_document": config["source_document"], "source_section": config["source_section"],
                "source_pages": config["source_pages"], "capability": config["capability"],
                "normative_strength": config["normative_strength"], "score_weight": config["score_weight"],
                "status": status, "evidence": evidence,
            }))
        for code, rule in known.items():
            if code not in seen:
                sanitized.append(self._result_from_rule(rule, "NOT_CHECKED", "Параметр не проверялся автоматически.", None, 0.0))
        return output.model_copy(update={"rule_results": sanitized})

    @staticmethod
    def _quote_exists(quote, source_text):
        normalize = lambda value: re.sub(r"\s+", " ", value.lower()).strip()
        return normalize(quote) in normalize(source_text)

    @staticmethod
    def _rule_prompt_item(rule):
        config = rule.configuration or {}
        return {"rule_code": config["rule_code"], "title": rule.title, "requirement": rule.description, **config}

    @staticmethod
    def _result_from_rule(rule, status, finding, recommendation, confidence):
        config = rule.configuration or {}
        return RuleCheckResult(
            rule_code=config["rule_code"], criterion_code=config["rule_code"].split(".")[0], title=rule.title,
            status=status, finding=finding, recommendation=recommendation, confidence=confidence, evidence=[],
            source_document=config["source_document"], source_section=config["source_section"],
            source_pages=config["source_pages"], capability=config["capability"],
            source_type=config.get("source_type"), methodology_owner=config.get("methodology_owner"),
            methodology_version=config.get("methodology_version"), is_official=config.get("is_official"),
            authority=config.get("authority"), normative_strength=config["normative_strength"], score_weight=config["score_weight"],
        )

    @staticmethod
    def _route_context(payload, criteria):
        terms = {
            "CD1": ("оглавление", "введение", "заключение", "список литературы", "приложение", "глава"),
            "CD2": ("актуаль", "разработан", "цель", "задач", "объект", "предмет", "новизн", "метод", "защит", "публикац"),
            "CD3": ("задач", "результат", "глава", "заключение", "методолог"),
            "CD4": ("заключение", "результат", "научн", "применим", "перспектив"),
            "CD5": ("список литературы", "[", "источник", "литератур"),
            "CD6": ("рисунок", "таблица", "формул", "где "),
            "CD7": tuple(),
        }
        if criteria == {"CD7"}:
            if payload.get("document_formatting"):
                return "[document_formatting] " + json.dumps(payload["document_formatting"], ensure_ascii=False)[:14000]
            return json.dumps({"page_count": payload.get("page_count")}, ensure_ascii=False)
        wanted = {term for code in criteria for term in terms.get(code, ())}
        items = []
        if payload.get("pages"):
            for page in payload["pages"]:
                for block in page.get("blocks") or []:
                    text = str(block.get("text") or "").strip()
                    if text and (not wanted or any(term in text.lower() for term in wanted)):
                        items.append(f"[page {page.get('page_number')} block {block.get('block_index')}] {text}")
        else:
            for paragraph in payload.get("paragraphs") or []:
                text = str(paragraph.get("text") or "").strip()
                if text and (not wanted or any(term in text.lower() for term in wanted)):
                    items.append(f"[paragraph {paragraph.get('paragraph_index')} style {paragraph.get('style')}] {text}")
            if "CD7" in criteria and payload.get("document_formatting"):
                items.append("[document_formatting] " + json.dumps(payload["document_formatting"], ensure_ascii=False))
        return "\n\n".join(items)[:14000]

    @staticmethod
    def _compact_package(methodology, rules, scoring):
        return {
            "methodology": {"name": methodology.name, "version": methodology.version},
            "scores": {code: {"score": value.score, "max_score": value.max_score, "status": value.status} for code, value in scoring["criteria"].items()},
            "coverage": scoring["coverage"],
            "findings": [item.finding for item in rules if item.status in {"FAIL", "PARTIAL"}][:20],
            "strengths": [item.finding for item in rules if item.status == "PASS"][:12],
            "recommendations": [item.recommendation for item in rules if item.recommendation][:15],
            "not_checked": [item.title for item in rules if item.status == "NOT_CHECKED"],
        }

    @staticmethod
    def _criterion_summary(code, rules):
        items = [item for item in rules if item.criterion_code == code]
        failed = [item for item in items if item.status in {"FAIL", "PARTIAL"}]
        if failed:
            return failed[0].finding
        if items and all(item.status == "NOT_CHECKED" for item in items):
            return "Критерий не проверялся автоматически из-за отсутствия достоверных технических данных."
        return "Проверенные требования в основном выполнены."


class CandidateDissertationAnalysisEngine:
    async def run(self, analysis_id, document_id, methodology_id, methodology_version, mode="standard"):
        if methodology_id != "CANDIDATE_DISSERTATION" or methodology_version != "1.0":
            raise AppError("ANALYSIS_ENGINE_METHODOLOGY_MISMATCH", "Исполнитель не поддерживает выбранную методологию", status_code=409)
        async with async_session_factory() as session:
            analysis = await session.get(Analysis, analysis_id)
            document = await session.get(Document, document_id)
            methodology = (await session.execute(select(Methodology).where(Methodology.code == methodology_id, Methodology.version == methodology_version))).scalar_one_or_none()
            if not analysis or not document or not methodology:
                raise AppError("ANALYSIS_CONTEXT_NOT_FOUND", "Не удалось загрузить контекст анализа", status_code=404)
            analysis.status = "processing"
            analysis.started_at = datetime.now(timezone.utc)
            await self._event(session, analysis, "prepare", 10, "Выделяю структуру и тематические разделы")
            assessment = Assessment(artifact_type="CANDIDATE_DISSERTATION", artifact_id=document.id, methodology_id=methodology.id, status="processing")
            session.add(assessment)
            await session.commit()
            await session.refresh(assessment)
            await self._event(session, analysis, "candidate_agents", 30, "Параллельно проверяю структуру, научный аппарат, логику, источники и оформление")
            result = await CandidateDissertationAgentFlow(session).execute(assessment, analysis, document)
            await self._event(session, analysis, "candidate_final", 90, "Формирую предварительный рекомендательный отчёт")
            session.add(AnalysisResult(analysis_id=analysis.id, result_json=result.model_dump(mode="json")))
            assessment.status = "completed"
            analysis.status = "completed"
            analysis.completed_at = datetime.now(timezone.utc)
            await self._event(session, analysis, "completed", 100, "Анализ завершён")
            return result

    @staticmethod
    async def _event(session, analysis, step, progress, message):
        analysis.current_step = step
        analysis.progress = progress
        session.add(AnalysisEvent(analysis_id=analysis.id, step_code=step, status="completed", progress=progress, message=message))
        await session.commit()

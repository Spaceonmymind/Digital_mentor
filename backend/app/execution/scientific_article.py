import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import async_session_factory
from app.execution.candidate_dissertation import CandidateDissertationAgentFlow
from app.execution.rule_preflight import deterministic_document_preflight
from app.execution.rule_schemas import CandidateAgentOutput, RuleBasedAgentOutput, RuleCheckResult
from app.methodology.models import Methodology
from app.methodology.seeds.scientific_article.data_v1 import DISCLAIMER


class ScientificArticleAgentFlow(CandidateDissertationAgentFlow):
    report_title = "Предварительный анализ научной статьи"
    report_key = "scientific_article_report"
    disclaimer = DISCLAIMER
    default_recommendation = "Уточнить соответствующий элемент научной статьи."

    def _precheck_rules(self, rules, payload, source_type):
        del source_type
        deterministic, pending = [], []
        preflight = self._deterministic_preflight(payload)
        for rule in rules:
            code = (rule.configuration or {}).get("rule_code")
            if code not in {"SA6.R01", "SA6.R02", "SA6.R03", "SA6.R04", "SA6.R05"}:
                pending.append(rule)
                continue
            status, finding, recommendation = self._bibliography_result(code, preflight)
            deterministic.append(self._result_from_rule(rule, status, finding, recommendation, 1.0).model_copy(update={
                "verification_basis": "DETERMINISTIC_CHECK",
                "searched_context": preflight["searched_context"],
            }))
        return deterministic, pending

    @staticmethod
    def _deterministic_preflight(payload):
        common = deterministic_document_preflight(payload)
        return {
            "bibliography_found": common["bibliography_found"], "entry_count": common["entry_count"],
            "entry_numbers": set(common["entry_numbers"]), "citations": set(common["citations"]),
            "author_year_citation_count": common["author_year_citation_count"],
            "missing_entries": common["missing_references"], "unused_entries": common["unused_references"],
            "headings": [item["location"] for item in common["headings"]],
            "searched_context": common["searched_locations"],
            "extraction_chars": common["extraction_diagnostics"]["chars"],
        }

    @staticmethod
    def _bibliography_result(code, data):
        if code == "SA6.R01":
            ok = data["bibliography_found"]
            return ("PASS" if ok else "FAIL", "Список литературы обнаружен." if ok else "В проверенном тексте список литературы не обнаружен.", "Добавьте явно обозначенный список литературы." if not ok else None)
        if code == "SA6.R02":
            count = len(data["citations"]) + data["author_year_citation_count"]
            ok = count > 0
            return ("PASS" if ok else "FAIL", f"Обнаружено внутритекстовых ссылок: {count}." if ok else "В проверенном основном тексте внутритекстовые ссылки не обнаружены.", "Добавьте внутритекстовые ссылки на используемые источники." if not ok else None)
        if code == "SA6.R03":
            if not data["citations"]:
                return "NOT_APPLICABLE", "Нумерованные внутритекстовые ссылки не обнаружены.", None
            ok = not data["missing_entries"]
            return ("PASS" if ok else "FAIL", "Все обнаруженные нумерованные ссылки сопоставлены с библиографией." if ok else f"Для ссылок {data['missing_entries']} не найдены библиографические записи.", "Добавьте или исправьте соответствующие записи списка литературы." if not ok else None)
        if code == "SA6.R04":
            if not data["entry_numbers"]:
                return "NOT_APPLICABLE", "Нумерованные библиографические записи не обнаружены.", None
            unused = data["unused_entries"]
            return ("PARTIAL" if unused else "PASS", f"Записи без обнаруженных ссылок: {unused}." if unused else "Все нумерованные записи имеют обнаруженные ссылки.", "Удалите неиспользуемые записи или добавьте ссылки на них." if unused else None)
        broken = data["missing_entries"]
        return ("FAIL" if broken else "PASS", f"Обнаружены повреждённые связи: {broken}." if broken else "Очевидных повреждённых нумерованных связей не обнаружено.", "Исправьте нумерацию ссылок и библиографии." if broken else None)

    def _sanitize_output(self, output, methodology, source_text, source_type, assigned_criteria=None):
        assigned_criteria = assigned_criteria or set((output.criterion_code or "").split(","))
        known = {indicator.configuration.get("rule_code"): indicator
                 for criterion in methodology.criteria if criterion.number in assigned_criteria
                 for indicator in criterion.indicators}
        sanitized, seen = [], set()
        for item in output.rule_results:
            rule = known.get(item.rule_code)
            if rule is None or item.rule_code in seen:
                continue
            seen.add(item.rule_code)
            config = rule.configuration or {}
            evidence = [e for e in item.evidence if e.quote and self._quote_exists(e.quote, source_text)]
            status = item.status
            basis = item.verification_basis
            searched = item.searched_context
            absence_verified = status == "FAIL" and basis in {"THEMATIC_SEARCH_NOT_FOUND", "DETERMINISTIC_CHECK"} and bool(searched)
            if status in {"PASS", "PARTIAL"} and not evidence and config.get("capability") in {"TEXT", "STRUCTURE", "CROSS_REFERENCE"}:
                status, basis = "NOT_CHECKED", "INSUFFICIENT_CONTEXT"
            if status == "FAIL" and not evidence and not absence_verified:
                status, basis = "NOT_CHECKED", "INSUFFICIENT_CONTEXT"
            sanitized.append(RuleCheckResult(
                rule_code=item.rule_code,
                criterion_code=item.rule_code.split(".")[0],
                title=rule.title,
                status=status,
                finding=item.finding,
                recommendation=item.recommendation,
                confidence=getattr(item, "confidence", 0.0),
                evidence=evidence,
                source_type=config.get("source_type"),
                source_document=None,
                source_section=None,
                source_pages=[],
                methodology_owner=config.get("methodology_owner"),
                methodology_version=config.get("methodology_version"),
                is_official=False,
                authority=None,
                verification_basis=basis,
                searched_context=searched,
                capability=config["capability"],
                normative_strength=config["normative_strength"],
                score_weight=config["score_weight"],
            ))
        for code, rule in known.items():
            if code not in seen:
                sanitized.append(self._result_from_rule(rule, "NOT_CHECKED", "Параметр не проверялся автоматически.", None, 0.0).model_copy(update={"verification_basis": "INSUFFICIENT_CONTEXT"}))
        return CandidateAgentOutput(
            criterion_code=output.criterion_code,
            summary=output.summary,
            rule_results=sanitized,
            strengths=getattr(output, "strengths", []),
            recommendations=getattr(output, "recommendations", []),
        )

    @staticmethod
    def _route_context(payload, criteria):
        terms = {
            "SA1": ("аннотац", "введен", "проблем", "актуаль", "цель", "задач"),
            "SA2": ("обзор", "исследован", "литератур", "подход", "ранее", "контекст"),
            "SA3": ("метод", "материал", "данн", "выборк", "процедур", "эксперимент"),
            "SA4": ("результат", "таблиц", "рисун", "получен", "показал", "выявлен"),
            "SA5": ("обсужден", "заключен", "вывод", "огранич", "дальнейш", "перспектив"),
            "SA6": ("литератур", "references", "[", "структур", "термин"),
        }
        wanted = {term for code in criteria for term in terms.get(code, ())}
        items = []
        for page in payload.get("pages") or []:
            for block in page.get("blocks") or []:
                value = str(block.get("text") or "").strip()
                if value and any(term in value.lower() for term in wanted):
                    items.append(f"[page {page.get('page_number')} block {block.get('block_index')}] {value}")
        for paragraph in payload.get("paragraphs") or []:
            value = str(paragraph.get("text") or "").strip()
            if value and any(term in value.lower() for term in wanted):
                items.append(f"[paragraph {paragraph.get('paragraph_index')}] {value}")
        if not items:
            source = str(payload.get("full_text") or "")
            head, tail = source[:5000], source[-3000:] if len(source) > 5000 else ""
            items = ["[limited fallback excerpt] " + head + ("\n" + tail if tail else "")]
        if "SA6" in criteria:
            preflight = ScientificArticleAgentFlow._deterministic_preflight(payload)
            items.insert(0, "[deterministic preflight] " + json.dumps({
                key: value for key, value in preflight.items() if key != "searched_context"
            }, ensure_ascii=False, default=list))
        return "\n\n".join(items)[:14000]


class ScientificArticleAnalysisEngine:
    async def run(self, analysis_id, document_id, methodology_id, methodology_version, mode="standard"):
        del mode
        if methodology_id != "SCIENTIFIC_ARTICLE" or methodology_version != "1.0":
            raise AppError("ANALYSIS_ENGINE_METHODOLOGY_MISMATCH", "Исполнитель не поддерживает выбранную методологию", status_code=409)
        async with async_session_factory() as session:
            analysis, document = await session.get(Analysis, analysis_id), await session.get(Document, document_id)
            methodology = (await session.execute(select(Methodology).where(Methodology.code == methodology_id, Methodology.version == methodology_version))).scalar_one_or_none()
            if not analysis or not document or not methodology:
                raise AppError("ANALYSIS_CONTEXT_NOT_FOUND", "Не удалось загрузить контекст анализа", status_code=404)
            analysis.status, analysis.started_at = "processing", datetime.now(timezone.utc)
            await self._event(session, analysis, "prepare", 10, "Выделяю структуру и тематические разделы статьи")
            assessment = Assessment(artifact_type="SCIENTIFIC_ARTICLE", artifact_id=document.id, methodology_id=methodology.id, status="processing")
            session.add(assessment)
            await session.commit()
            await session.refresh(assessment)
            await self._event(session, analysis, "article_agents", 30, "Параллельно проверяю содержание, методологию, результаты и источники")
            result = await ScientificArticleAgentFlow(session).execute(assessment, analysis, document)
            await self._event(session, analysis, "article_final", 90, "Формирую предварительный анализ научной статьи")
            session.add(AnalysisResult(analysis_id=analysis.id, result_json=result.model_dump(mode="json")))
            assessment.status, analysis.status, analysis.completed_at = "completed", "completed", datetime.now(timezone.utc)
            await self._event(session, analysis, "completed", 100, "Анализ завершён")
            return result

    @staticmethod
    async def _event(session, analysis, step, progress, message):
        analysis.current_step, analysis.progress = step, progress
        session.add(AnalysisEvent(analysis_id=analysis.id, step_code=step, status="completed", progress=progress, message=message))
        await session.commit()

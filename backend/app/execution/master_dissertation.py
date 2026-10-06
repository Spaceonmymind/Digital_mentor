import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import async_session_factory
from app.execution.graduation_thesis import GraduationThesisAgentFlow
from app.execution.rule_preflight import deterministic_document_preflight
from app.methodology.models import Methodology
from app.methodology.seeds.master_dissertation.data_v1 import DISCLAIMER


class MasterDissertationAgentFlow(GraduationThesisAgentFlow):
    report_title = "Предварительный анализ магистерской диссертации"
    report_key = "master_dissertation_report"
    disclaimer = DISCLAIMER
    default_recommendation = "Уточнить соответствующий элемент магистерской диссертации."

    def _precheck_rules(self, rules, payload, source_type):
        del source_type
        preflight = deterministic_document_preflight(payload)
        text = str(payload.get("full_text") or "").lower()
        done, pending = [], []
        bibliography_map = {"MD6.R04": "GT6.R02", "MD6.R05": "GT6.R03", "MD6.R06": "GT6.R04", "MD6.R07": "GT6.R05"}
        object_map = {"MD6.R08": "figures", "MD6.R09": "tables", "MD6.R10": "formulas", "MD6.R11": "applications"}
        for rule in rules:
            code = (rule.configuration or {}).get("rule_code")
            if code in bibliography_map:
                status, finding, recommendation = self._bibliography_check(bibliography_map[code], preflight)
                done.append(self._deterministic_result(rule, status, finding, recommendation, preflight))
            elif code in object_map:
                if preflight[object_map[code]]:
                    pending.append(rule)
                else:
                    done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Соответствующие объекты в доступном тексте не обнаружены.", None, preflight))
            elif code == "MD1.R08" and not re.search(r"\b(гипотез|исследовательск\w*\s+вопрос)\w*", text):
                done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Явная гипотеза или исследовательский вопрос в доступном тексте не заявлены.", None, preflight))
            elif code == "MD4.R06" and not re.search(r"\b(новизн|новый\s+(?:подход|метод|результат|вклад))\w*", text):
                done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Заявление о научной новизне в доступном тексте не обнаружено; отсутствие такого заявления само по себе не является нарушением.", None, preflight))
            elif code == "MD4.R08":
                character = getattr(self, "work_character", {"type": "MIXED", "confidence": 0})
                if character["type"] == "SOFTWARE" and character["confidence"] >= 0.45:
                    pending.append(rule)
                elif character["type"] != "MIXED" and character["confidence"] >= 0.65:
                    done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Программная реализация в доступном тексте не подтверждена.", None, preflight))
                else:
                    done.append(self._result_from_rule(rule, "NOT_CHECKED", "Применимость проверки программной реализации нельзя определить надёжно.", None, 0.0).model_copy(update={"verification_basis": "INSUFFICIENT_CONTEXT", "searched_context": preflight["searched_locations"]}))
            elif code == "MD5.R08" and not re.search(r"\b(статист|выборк|корреляц|регресси|значимост|p[- ]?value|дисперси)\w*", text):
                done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Количественные результаты, требующие отдельной обработки, не подтверждены.", None, preflight))
            else:
                pending.append(rule)
        return done, pending

    def _route_context(self, payload, criteria):
        terms = {
            "MD1": ("введен", "актуаль", "проблем", "цель", "задач", "объект", "предмет", "гипотез", "вопрос"),
            "MD2": ("теорет", "обзор", "литератур", "подход", "сравнен", "исследован", "противореч"),
            "MD3": ("метод", "методолог", "данн", "материал", "выборк", "модел", "алгоритм", "эксперимент", "процедур"),
            "MD4": ("вклад", "новизн", "результат", "разработ", "предлож", "реализ", "модел", "алгоритм", "апробац"),
            "MD5": ("результат", "обсужден", "интерпрет", "огранич", "заключен", "вывод", "перспектив"),
            "MD6": ("цель", "задач", "метод", "результат", "заключен", "литератур", "references", "таблиц", "рисун", "формул", "приложен", "["),
        }
        wanted = {term for code in criteria for term in terms.get(code, ())}
        character_terms = {"SOFTWARE": ("код", "модул", "архитектур", "тест"), "RESEARCH": ("эксперимент", "выборк", "гипотез", "эмпирич"),
            "PROJECT": ("проект", "прототип", "внедрен"), "ANALYTICAL": ("анализ", "расчёт", "оценк")}
        wanted.update(character_terms.get(getattr(self, "work_character", {"type": "MIXED"})["type"], ()))
        preflight = deterministic_document_preflight(payload)
        selected = [f"[{b['location']}] {b['text']}" for b in preflight["blocks"] if any(term in b["text"].lower() for term in wanted)]
        if not selected:
            selected = [f"[{b['location']}] {b['text']}" for b in (preflight["blocks"][:25] + preflight["blocks"][-15:])]
        if "MD6" in criteria:
            summary = {k: v for k, v in preflight.items() if k not in {"blocks", "searched_locations", "bibliography_entries", "headings", "section_candidates", "tables", "figures", "formulas", "applications", "captions_and_identifiers"}}
            selected.insert(0, "[deterministic preflight] " + json.dumps(summary, ensure_ascii=False))
        return "\n\n".join(selected)[:14000]

    @staticmethod
    def _compact_package(methodology, rules, scoring):
        package = GraduationThesisAgentFlow._compact_package(methodology, rules, scoring)
        package["independent_contribution_candidates"] = [{"finding": item.finding, "evidence": [e.model_dump(mode="json") for e in item.evidence]}
            for item in rules if item.rule_code == "MD4.R01" and item.status in {"PASS", "PARTIAL"}]
        package["research_chain"] = [{"rule": item.rule_code, "finding": item.finding,
            "evidence": [e.model_dump(mode="json") for e in item.evidence]}
            for item in rules if item.criterion_code in {"MD1", "MD3", "MD4", "MD5", "MD6"} and item.status != "NOT_APPLICABLE"]
        return package

    def _report_extras(self, rule_results, final_output, payload):
        del payload
        candidates = [item for item in rule_results if item.rule_code == "MD4.R01" and item.status in {"PASS", "PARTIAL"}]
        text = final_output.represented_result or (candidates[0].finding if candidates else "Системе не удалось однозначно определить самостоятельный вклад по доступному тексту.")
        if candidates and not text.lower().startswith("в тексте"):
            text = "В тексте представлен как самостоятельный вклад автора: " + text[0].lower() + text[1:]
        return {"represented_result": {"title": "Самостоятельный вклад, представленный в работе", "text": text,
            "evidence": [e.model_dump(mode="json") for item in candidates for e in item.evidence]},
            "internal_work_character": getattr(self, "work_character", {"type": "MIXED", "confidence": 0.0})}


class MasterDissertationAnalysisEngine:
    async def run(self, analysis_id, document_id, methodology_id, methodology_version, mode="standard"):
        del mode
        if methodology_id != "MASTER_DISSERTATION" or methodology_version != "1.0":
            raise AppError("ANALYSIS_ENGINE_METHODOLOGY_MISMATCH", "Исполнитель не поддерживает выбранную методологию", status_code=409)
        async with async_session_factory() as session:
            analysis, document = await session.get(Analysis, analysis_id), await session.get(Document, document_id)
            methodology = (await session.execute(select(Methodology).where(Methodology.code == methodology_id, Methodology.version == methodology_version))).scalar_one_or_none()
            if not analysis or not document or not methodology:
                raise AppError("ANALYSIS_CONTEXT_NOT_FOUND", "Не удалось загрузить контекст анализа", status_code=404)
            analysis.status, analysis.started_at = "processing", datetime.now(timezone.utc)
            await self._event(session, analysis, "prepare", 10, "Выделяю исследовательскую структуру магистерской диссертации")
            assessment = Assessment(artifact_type="MASTER_THESIS", artifact_id=document.id, methodology_id=methodology.id, status="processing")
            session.add(assessment); await session.commit(); await session.refresh(assessment)
            await self._event(session, analysis, "master_agents", 30, "Параллельно проверяю постановку, методологию, вклад, результаты и целостность")
            result = await MasterDissertationAgentFlow(session).execute(assessment, analysis, document)
            await self._event(session, analysis, "master_final", 90, "Формирую предварительный анализ магистерской диссертации")
            session.add(AnalysisResult(analysis_id=analysis.id, result_json=result.model_dump(mode="json")))
            assessment.status, analysis.status, analysis.completed_at = "completed", "completed", datetime.now(timezone.utc)
            await self._event(session, analysis, "completed", 100, "Анализ завершён")
            return result

    @staticmethod
    async def _event(session, analysis, step, progress, message):
        analysis.current_step, analysis.progress = step, progress
        session.add(AnalysisEvent(analysis_id=analysis.id, step_code=step, status="completed", progress=progress, message=message))
        await session.commit()

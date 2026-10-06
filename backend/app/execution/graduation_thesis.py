import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import async_session_factory
from app.execution.rule_preflight import deterministic_document_preflight
from app.execution.scientific_article import ScientificArticleAgentFlow
from app.methodology.models import Methodology
from app.methodology.seeds.graduation_thesis.data_v1 import DISCLAIMER


class GraduationThesisAgentFlow(ScientificArticleAgentFlow):
    report_title = "Предварительный анализ выпускной квалификационной работы"
    report_key = "graduation_thesis_report"
    disclaimer = DISCLAIMER
    default_recommendation = "Уточнить соответствующий элемент выпускной квалификационной работы."

    async def execute(self, assessment, analysis, document):
        from app.services.document_context import load_extracted_payload
        self.work_character = self._infer_work_character(load_extracted_payload(document))
        return await super().execute(assessment, analysis, document)

    @staticmethod
    def _infer_work_character(payload):
        text = str(payload.get("full_text") or "").lower()
        terms = {
            "SOFTWARE": ("программ", "код", "интерфейс", "архитектур", "тестирован", "алгоритм"),
            "RESEARCH": ("исследован", "эксперимент", "выборк", "гипотез", "эмпирич"),
            "PROJECT": ("проект", "прототип", "проектирован", "внедрен", "разработан"),
            "ANALYTICAL": ("анализ", "оценк", "сравнен", "рекомендац", "расчёт"),
        }
        scores = {kind: sum(text.count(term) for term in words) for kind, words in terms.items()}
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best, second = ordered[0], ordered[1]
        total = sum(scores.values())
        confidence = 0.0 if total == 0 else min(1.0, (best[1] - second[1] + best[1]) / max(total, 1))
        kind = best[0] if best[1] >= 2 and confidence >= 0.45 else "MIXED"
        return {"type": kind, "confidence": round(confidence, 3), "signals": scores}

    def _precheck_rules(self, rules, payload, source_type):
        del source_type
        preflight = deterministic_document_preflight(payload)
        done, pending = [], []
        for rule in rules:
            code = (rule.configuration or {}).get("rule_code")
            if code in {"GT6.R02", "GT6.R03", "GT6.R04", "GT6.R05"}:
                status, finding, recommendation = self._bibliography_check(code, preflight)
                done.append(self._deterministic_result(rule, status, finding, recommendation, preflight))
            elif code in {"GT6.R06", "GT6.R07", "GT6.R08", "GT6.R09"}:
                key = {"GT6.R06": "figures", "GT6.R07": "tables", "GT6.R08": "formulas", "GT6.R09": "applications"}[code]
                if not preflight[key]:
                    done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Соответствующие объекты в доступном тексте не обнаружены.", None, preflight))
                else:
                    pending.append(rule)
            elif code == "GT4.R07":
                character = getattr(self, "work_character", {"type": "MIXED", "confidence": 0})
                if character["type"] == "SOFTWARE" and character["confidence"] >= 0.45:
                    pending.append(rule)
                elif character["type"] != "MIXED" and character["confidence"] >= 0.65:
                    done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Реализованный программный продукт в доступном тексте не подтверждён.", None, preflight))
                else:
                    result = self._result_from_rule(rule, "NOT_CHECKED", "Применимость проверки реализации и тестирования нельзя определить надёжно.", None, 0.0)
                    done.append(result.model_copy(update={"verification_basis": "INSUFFICIENT_CONTEXT", "searched_context": preflight["searched_locations"]}))
            else:
                pending.append(rule)
        return done, pending

    def _deterministic_result(self, rule, status, finding, recommendation, preflight):
        return self._result_from_rule(rule, status, finding, recommendation, 1.0).model_copy(update={
            "verification_basis": "DETERMINISTIC_CHECK", "searched_context": preflight["searched_locations"]})

    @staticmethod
    def _bibliography_check(code, data):
        if code == "GT6.R02":
            ok = data["bibliography_found"]
            return ("PASS" if ok else "FAIL", "Список литературы обнаружен." if ok else "В проверенном тексте список литературы не обнаружен.", "Добавьте явно обозначенный список литературы." if not ok else None)
        if code == "GT6.R03":
            count = len(data["citations"]) + data["author_year_citation_count"]
            return ("PASS" if count else "FAIL", f"Обнаружено внутритекстовых ссылок: {count}." if count else "Внутритекстовые ссылки не обнаружены.", "Свяжите используемые источники с текстом работы." if not count else None)
        if code == "GT6.R04":
            if not data["citations"]:
                return "NOT_APPLICABLE", "Нумерованные ссылки для сопоставления не обнаружены.", None
            missing = data["missing_references"]
            return ("FAIL" if missing else "PASS", f"Не найдены записи для ссылок: {missing}." if missing else "Обнаруженные нумерованные ссылки сопоставлены с записями.", "Исправьте список литературы или номера ссылок." if missing else None)
        unused = data["unused_references"]
        return ("PARTIAL" if unused else "PASS", f"Записи без обнаруженных ссылок: {unused}." if unused else "Неиспользованные нумерованные записи не обнаружены.", "Удалите записи или добавьте ссылки на них." if unused else None)

    def _route_context(self, payload, criteria):
        terms = {
            "GT1": ("аннотац", "введен", "актуаль", "проблем", "цель", "задач", "объект", "предмет", "теорет", "анализ"),
            "GT2": ("теорет", "анализ", "обзор", "источник", "подход", "существующ", "глава"),
            "GT3": ("метод", "модел", "алгоритм", "материал", "данн", "проектн", "процедур", "архитектур"),
            "GT4": ("разработ", "реализ", "предлож", "создан", "результат", "эксперимент", "расчёт", "прототип", "тестирован", "апробац"),
            "GT5": ("цель", "задач", "результат", "заключен", "вывод", "выполнен", "огранич"),
            "GT6": ("литератур", "references", "таблиц", "рисун", "формул", "приложен", "["),
        }
        wanted = {term for code in criteria for term in terms.get(code, ())}
        character_terms = {
            "SOFTWARE": ("код", "модул", "интерфейс", "архитектур", "тест"),
            "RESEARCH": ("эксперимент", "выборк", "гипотез", "эмпирич"),
            "PROJECT": ("проект", "прототип", "внедрен", "проектирован"),
            "ANALYTICAL": ("анализ", "расчёт", "оценк", "рекомендац"),
        }
        character = getattr(self, "work_character", {"type": "MIXED"})["type"]
        wanted.update(character_terms.get(character, ()))
        preflight = deterministic_document_preflight(payload)
        selected = [f"[{block['location']}] {block['text']}" for block in preflight["blocks"] if any(term in block["text"].lower() for term in wanted)]
        if not selected:
            blocks = preflight["blocks"]
            selected = [f"[{item['location']}] {item['text']}" for item in (blocks[:25] + blocks[-15:])]
        if "GT6" in criteria:
            summary = {key: value for key, value in preflight.items() if key not in {"blocks", "searched_locations", "bibliography_entries", "headings", "section_candidates", "tables", "figures", "formulas", "applications", "captions_and_identifiers"}}
            selected.insert(0, "[deterministic preflight] " + json.dumps(summary, ensure_ascii=False))
        return "\n\n".join(selected)[:14000]

    @staticmethod
    def _compact_package(methodology, rules, scoring):
        package = ScientificArticleAgentFlow._compact_package(methodology, rules, scoring)
        package["represented_result_candidates"] = [{"finding": item.finding, "evidence": [e.model_dump(mode="json") for e in item.evidence]}
            for item in rules if item.criterion_code == "GT4" and item.rule_code == "GT4.R01" and item.status in {"PASS", "PARTIAL"}]
        package["task_result_conclusion_mapping"] = [{"rule": item.rule_code, "finding": item.finding,
            "evidence": [e.model_dump(mode="json") for e in item.evidence]}
            for item in rules if item.criterion_code == "GT5"]
        return package

    def _report_extras(self, rule_results, final_output, payload):
        del payload
        candidates = [item for item in rule_results if item.rule_code == "GT4.R01" and item.status in {"PASS", "PARTIAL"}]
        if final_output.represented_result:
            text = final_output.represented_result
        elif candidates:
            text = candidates[0].finding
        else:
            text = "Системе не удалось однозначно определить самостоятельный результат по доступному тексту."
        if candidates and not text.lower().startswith("в тексте"):
            text = "В тексте представлен как результат автора: " + text[0].lower() + text[1:]
        return {"represented_result": {"title": "Результат, представленный в работе", "text": text,
            "evidence": [e.model_dump(mode="json") for item in candidates for e in item.evidence]},
            "internal_work_character": getattr(self, "work_character", {"type": "MIXED", "confidence": 0.0})}


class GraduationThesisAnalysisEngine:
    async def run(self, analysis_id, document_id, methodology_id, methodology_version, mode="standard"):
        del mode
        if methodology_id != "GRADUATION_THESIS" or methodology_version != "1.0":
            raise AppError("ANALYSIS_ENGINE_METHODOLOGY_MISMATCH", "Исполнитель не поддерживает выбранную методологию", status_code=409)
        async with async_session_factory() as session:
            analysis, document = await session.get(Analysis, analysis_id), await session.get(Document, document_id)
            methodology = (await session.execute(select(Methodology).where(Methodology.code == methodology_id, Methodology.version == methodology_version))).scalar_one_or_none()
            if not analysis or not document or not methodology:
                raise AppError("ANALYSIS_CONTEXT_NOT_FOUND", "Не удалось загрузить контекст анализа", status_code=404)
            analysis.status, analysis.started_at = "processing", datetime.now(timezone.utc)
            await self._event(session, analysis, "prepare", 10, "Выделяю структуру и смысловые части ВКР")
            assessment = Assessment(artifact_type="BACHELOR_SPECIALIST_THESIS", artifact_id=document.id, methodology_id=methodology.id, status="processing")
            session.add(assessment); await session.commit(); await session.refresh(assessment)
            await self._event(session, analysis, "graduation_agents", 30, "Параллельно проверяю постановку, подход, результат, выводы и источники")
            result = await GraduationThesisAgentFlow(session).execute(assessment, analysis, document)
            await self._event(session, analysis, "graduation_final", 90, "Формирую предварительный анализ ВКР")
            session.add(AnalysisResult(analysis_id=analysis.id, result_json=result.model_dump(mode="json")))
            assessment.status, analysis.status, analysis.completed_at = "completed", "completed", datetime.now(timezone.utc)
            await self._event(session, analysis, "completed", 100, "Анализ завершён")
            return result

    @staticmethod
    async def _event(session, analysis, step, progress, message):
        analysis.current_step, analysis.progress = step, progress
        session.add(AnalysisEvent(analysis_id=analysis.id, step_code=step, status="completed", progress=progress, message=message))
        await session.commit()

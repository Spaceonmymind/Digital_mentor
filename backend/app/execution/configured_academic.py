import json
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.assessment.models import Assessment
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisEvent, AnalysisResult, Document
from app.db.session import async_session_factory
from app.execution.master_dissertation import MasterDissertationAgentFlow
from app.execution.rule_preflight import deterministic_document_preflight
from app.methodology.models import Methodology


class ConfiguredAcademicAgentFlow(MasterDissertationAgentFlow):
    criterion_terms = {}
    result_rule_prefix = ""
    result_title = "Основной результат"
    use_work_character = False

    async def execute(self, assessment, analysis, document):
        if self.use_work_character:
            return await super().execute(assessment, analysis, document)
        from app.execution.candidate_dissertation import CandidateDissertationAgentFlow
        return await CandidateDissertationAgentFlow.execute(self, assessment, analysis, document)

    def _precheck_rules(self, rules, payload, source_type):
        del source_type
        preflight = deterministic_document_preflight(payload)
        text = str(payload.get("full_text") or "").lower()
        done, pending = [], []
        for rule in rules:
            cfg = rule.configuration or {}; applicability = cfg.get("applicability", "always")
            if applicability != "always":
                keyword = next((word for word in re.findall(r"[а-яёa-z]{5,}", rule.title.lower()) if word in text), None)
                if not keyword:
                    done.append(self._deterministic_result(rule, "NOT_APPLICABLE", "Условие применимости в доступном тексте не подтверждено.", None, preflight)); continue
            if cfg.get("capability") == "NOT_AUTOMATICALLY_VERIFIABLE":
                done.append(self._result_from_rule(rule, "NOT_CHECKED", "Проверка требует внешнего подтверждения.", None, 0.0).model_copy(update={"verification_basis":"EXTERNAL_VERIFICATION_REQUIRED","searched_context":preflight["searched_locations"]}))
            else: pending.append(rule)
        return done, pending

    def _route_context(self, payload, criteria):
        wanted={term for code in criteria for term in self.criterion_terms.get(code,())}
        if self.use_work_character:
            character_terms={"SOFTWARE":("код","модул","архитектур","тест"),"RESEARCH":("эксперимент","выборк","гипотез","эмпирич"),"PROJECT":("проект","прототип","внедрен"),"ANALYTICAL":("анализ","расчёт","оценк")}
            wanted.update(character_terms.get(getattr(self,"work_character",{"type":"MIXED"})["type"],()))
        preflight=deterministic_document_preflight(payload)
        selected=[f"[{b['location']}] {b['text']}" for b in preflight["blocks"] if any(term in b["text"].lower() for term in wanted)]
        if not selected: selected=[f"[{b['location']}] {b['text']}" for b in preflight["blocks"][:30]+preflight["blocks"][-15:]]
        if any(code.endswith(("5","6","7")) for code in criteria):
            summary={k:v for k,v in preflight.items() if k not in {"blocks","searched_locations","bibliography_entries","headings","section_candidates","tables","figures","formulas","applications","captions_and_identifiers"}}
            selected.insert(0,"[deterministic preflight] "+json.dumps(summary,ensure_ascii=False))
        return "\n\n".join(selected)[:14000]

    @staticmethod
    def _compact_package(methodology, rules, scoring):
        from app.execution.candidate_dissertation import CandidateDissertationAgentFlow
        return CandidateDissertationAgentFlow._compact_package(methodology, rules, scoring)

    def _report_extras(self, rule_results, final_output, payload):
        del payload
        candidates=[x for x in rule_results if x.rule_code.startswith(self.result_rule_prefix) and x.status in {"PASS","PARTIAL"}]
        text=final_output.represented_result or (candidates[0].finding if candidates else "По доступному тексту результат нельзя определить однозначно.")
        return {"represented_result":{"title":self.result_title,"text":text,"evidence":[e.model_dump(mode="json") for x in candidates for e in x.evidence]}}


class ConfiguredAcademicAnalysisEngine:
    methodology_code=""; methodology_version="1.0"; artifact_type=""; flow_class=ConfiguredAcademicAgentFlow
    prepare_message="Подготавливаю документ"; agents_message="Параллельно выполняю тематические проверки"; final_message="Формирую предварительный отчёт"
    async def run(self, analysis_id, document_id, methodology_id, methodology_version, mode="standard"):
        del mode
        if methodology_id != self.methodology_code or methodology_version != self.methodology_version:
            raise AppError("ANALYSIS_ENGINE_METHODOLOGY_MISMATCH","Исполнитель не поддерживает выбранную методологию",status_code=409)
        async with async_session_factory() as session:
            analysis,document=await session.get(Analysis,analysis_id),await session.get(Document,document_id)
            methodology=(await session.execute(select(Methodology).where(Methodology.code==methodology_id,Methodology.version==methodology_version))).scalar_one_or_none()
            if not analysis or not document or not methodology: raise AppError("ANALYSIS_CONTEXT_NOT_FOUND","Не удалось загрузить контекст анализа",status_code=404)
            analysis.status,analysis.started_at="processing",datetime.now(timezone.utc)
            await self._event(session,analysis,"prepare",10,self.prepare_message)
            assessment=Assessment(artifact_type=self.artifact_type,artifact_id=document.id,methodology_id=methodology.id,status="processing")
            session.add(assessment); await session.commit(); await session.refresh(assessment)
            await self._event(session,analysis,"thematic_agents",30,self.agents_message)
            result=await self.flow_class(session).execute(assessment,analysis,document)
            await self._event(session,analysis,"final",90,self.final_message)
            session.add(AnalysisResult(analysis_id=analysis.id,result_json=result.model_dump(mode="json")))
            assessment.status,analysis.status,analysis.completed_at="completed","completed",datetime.now(timezone.utc)
            await self._event(session,analysis,"completed",100,"Анализ завершён")
            return result
    @staticmethod
    async def _event(session,analysis,step,progress,message):
        analysis.current_step,analysis.progress=step,progress
        session.add(AnalysisEvent(analysis_id=analysis.id,step_code=step,status="completed",progress=progress,message=message)); await session.commit()

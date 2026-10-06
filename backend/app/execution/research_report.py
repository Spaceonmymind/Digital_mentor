from app.execution.configured_academic import ConfiguredAcademicAgentFlow, ConfiguredAcademicAnalysisEngine
from app.methodology.seeds.research_report.data_v1 import DISCLAIMER
class ResearchReportAgentFlow(ConfiguredAcademicAgentFlow):
    report_title="Предварительный анализ отчёта по НИР"; report_key="research_report_report"; disclaimer=DISCLAIMER
    result_rule_prefix="RR4"; result_title="Основные результаты НИР"; use_work_character=True
    criterion_terms={"RR1":("проблем","актуаль","цель","задач"),"RR2":("теорет","методолог","источник","литератур"),"RR3":("этап","метод","данн","процедур"),"RR4":("результат","вклад","артефакт"),"RR5":("интерпрет","огранич","вывод","перспектив"),"RR6":("структур","литератур","ссылк","воспроизвод")}
class ResearchReportAnalysisEngine(ConfiguredAcademicAnalysisEngine):
    methodology_code="RESEARCH_REPORT"; artifact_type="RESEARCH_REPORT"; flow_class=ResearchReportAgentFlow

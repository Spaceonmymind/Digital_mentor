from app.execution.configured_academic import ConfiguredAcademicAgentFlow, ConfiguredAcademicAnalysisEngine
from app.methodology.seeds.internship_report.data_v1 import DISCLAIMER
class InternshipReportAgentFlow(ConfiguredAcademicAgentFlow):
    report_title="Предварительный анализ отчёта по практике"; report_key="internship_report_report"; disclaimer=DISCLAIMER
    result_rule_prefix="IR3"; result_title="Что выполнено в ходе практики"
    criterion_terms={"IR1":("практик","цель","задач","срок"),"IR2":("организац","подраздел","объект","должност"),"IR3":("выполн","работ","задани","инструмент","этап"),"IR4":("результат","навык","компетен","трудност"),"IR5":("итог","вывод","приложен","источник")}
class InternshipReportAnalysisEngine(ConfiguredAcademicAnalysisEngine):
    methodology_code="INTERNSHIP_REPORT"; artifact_type="PRACTICE_REPORT"; flow_class=InternshipReportAgentFlow

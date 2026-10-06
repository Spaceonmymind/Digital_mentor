from app.execution.configured_academic import ConfiguredAcademicAgentFlow, ConfiguredAcademicAnalysisEngine
from app.methodology.seeds.course_paper.data_v1 import DISCLAIMER
class CoursePaperAgentFlow(ConfiguredAcademicAgentFlow):
    report_title="Предварительный анализ курсовой работы"; report_key="course_paper_report"; disclaimer=DISCLAIMER
    result_rule_prefix="CP3"; result_title="Основной результат работы"; use_work_character=True
    criterion_terms={"CP1":("актуаль","цель","задач","тем"),"CP2":("теорет","источник","литератур","подход"),"CP3":("анализ","практич","метод","данн","результат"),"CP4":("вывод","результат","огранич","предлож"),"CP5":("заключен","литератур","ссылк","таблиц","рисун","приложен")}
class CoursePaperAnalysisEngine(ConfiguredAcademicAnalysisEngine):
    methodology_code="COURSE_PAPER"; artifact_type="COURSE_WORK"; flow_class=CoursePaperAgentFlow

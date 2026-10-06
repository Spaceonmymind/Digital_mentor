from app.execution.configured_academic import ConfiguredAcademicAgentFlow, ConfiguredAcademicAnalysisEngine
from app.methodology.seeds.doctoral_dissertation.data_v1 import DISCLAIMER
class DoctoralDissertationAgentFlow(ConfiguredAcademicAgentFlow):
    report_title="Предварительный анализ докторской диссертации"; report_key="doctoral_dissertation_report"; disclaimer=DISCLAIMER
    result_rule_prefix="DD4"; result_title="Научный вклад, заявленный в работе"; use_work_character=True
    criterion_terms={"DD1":("проблем","актуаль","цель","задач","масштаб"),"DD2":("теорет","обзор","разрыв","противореч"),"DD3":("метод","данн","выборк","валид"),"DD4":("вклад","новизн","положен","автор"),"DD5":("результат","достовер","апробац","публикац"),"DD6":("значим","интерпрет","огранич","перспектив"),"DD7":("оглавлен","введен","заключен","литератур","ссылк")}
class DoctoralDissertationAnalysisEngine(ConfiguredAcademicAnalysisEngine):
    methodology_code="DOCTORAL_DISSERTATION"; artifact_type="DOCTORAL_DISSERTATION"; flow_class=DoctoralDissertationAgentFlow

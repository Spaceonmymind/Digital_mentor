from app.execution.configured_academic import ConfiguredAcademicAgentFlow, ConfiguredAcademicAnalysisEngine
from app.methodology.seeds.dissertation_abstract.data_v1 import DISCLAIMER
class DissertationAbstractAgentFlow(ConfiguredAcademicAgentFlow):
    report_title="Предварительный анализ автореферата диссертации"; report_key="dissertation_abstract_report"; disclaimer=DISCLAIMER
    result_rule_prefix="DA3"; result_title="Ключевые положения, представленные в автореферате"
    criterion_terms={"DA1":("автореферат","характеристик","содержание","заключен"),"DA2":("актуаль","цель","задач","объект","метод"),"DA3":("новизн","значим","положен","вклад"),"DA4":("глав","задач","результат","новизн"),"DA5":("итог","рекомендац","перспектив","публикац"),"DA6":("рукопис","специальност","степен","совет","год")}
class DissertationAbstractAnalysisEngine(ConfiguredAcademicAnalysisEngine):
    methodology_code="DISSERTATION_ABSTRACT"; artifact_type="DISSERTATION_ABSTRACT"; flow_class=DissertationAbstractAgentFlow

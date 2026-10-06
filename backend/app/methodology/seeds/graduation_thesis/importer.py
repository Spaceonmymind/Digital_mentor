from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate, WorkType
from app.methodology.registry import WORK_TYPE_BY_CODE
from app.methodology.seeds.graduation_thesis import data_v1


async def ensure_graduation_thesis_seed(session: AsyncSession) -> Methodology:
    definition = WORK_TYPE_BY_CODE["BACHELOR_SPECIALIST_THESIS"]
    work_type = await session.get(WorkType, definition.code) or WorkType(code=definition.code)
    work_type.display_name, work_type.sort_order = definition.display_name, definition.sort_order
    work_type.description = "Предварительный анализ ВКР бакалавра или специалиста по внутренней методологии Digital Mentor."
    work_type.status, work_type.configuration = "AVAILABLE", {}
    session.add(work_type)
    await session.flush()
    methodology = (await session.execute(select(Methodology).where(Methodology.code == "GRADUATION_THESIS", Methodology.version == "1.0"))).scalar_one_or_none()
    methodology = methodology or Methodology(id=data_v1.METHODOLOGY_ID, code="GRADUATION_THESIS")
    methodology.work_type_code, methodology.name = "BACHELOR_SPECIALIST_THESIS", "ВКР бакалавра / специалиста"
    methodology.description = "Внутренняя методология предварительного анализа выпускной квалификационной работы Digital Mentor."
    methodology.version, methodology.is_active, methodology.is_demo = "1.0", True, False
    methodology.source, methodology.status, methodology.max_score = data_v1.SOURCE, "ACTIVE", 60
    methodology.applicable_formats = ["pdf", "docx"]
    methodology.configuration = {"execution_profile": "graduation_thesis", "source_type": data_v1.SOURCE_TYPE,
        "methodology_owner": "Digital Mentor", "is_official": False, "authority": None,
        "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 60},
        "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
        "evidence_rules": {"validate_quotes": True, "allow_verified_absence": True}, "limitations": data_v1.LIMITATIONS,
        "report_configuration": {"title": "Предварительный анализ выпускной квалификационной работы", "disclaimer": data_v1.DISCLAIMER}}
    session.add(methodology)
    await session.flush()
    prompt_ids = {}
    for item in data_v1.PROMPTS:
        prompt = await session.get(PromptTemplate, item["id"]) or PromptTemplate(id=item["id"], methodology_id=methodology.id)
        prompt.stage, prompt.system_prompt, prompt.user_template = item["stage"], item["system_prompt"], item["user_template"]
        prompt.version, prompt.is_demo, prompt.source = item["version"], False, data_v1.SOURCE
        session.add(prompt); prompt_ids[item["stage"]] = prompt.id
    for item in data_v1.CRITERIA:
        criterion_id = f"graduation-thesis-1-0-{item['number'].lower()}"
        criterion = await session.get(MethodologyCriterion, criterion_id) or MethodologyCriterion(id=criterion_id, methodology_id=methodology.id)
        criterion.number, criterion.title, criterion.description = item["number"], item["title"], item["description"]
        criterion.weight, criterion.max_score, criterion.required = None, 10, True
        criterion.configuration, criterion.order_index = {"score_from": "checked_applicable_rules"}, item["order_index"]
        criterion.is_demo, criterion.source, criterion.version = False, data_v1.SOURCE, data_v1.VERSION
        session.add(criterion)
        for order, rule in enumerate(item["rules"], 1):
            indicator = await session.get(MethodologyIndicator, rule["id"]) or MethodologyIndicator(id=rule["id"], criterion_id=criterion.id)
            indicator.title, indicator.description, indicator.expected_result = rule["title"], rule["description"], rule["expected_result"]
            indicator.weight, indicator.order_index = 1.0, order
            indicator.required = rule["configuration"]["normative_strength"] == "REQUIRED"
            indicator.configuration = {"rule_code": rule["code"], **rule["configuration"]}
            indicator.is_demo, indicator.source, indicator.version = False, data_v1.SOURCE, data_v1.VERSION
            session.add(indicator)
    for agent_id, code, name, stage, order, mode, role, criteria in data_v1.AGENTS:
        agent = await session.get(MethodologyAgent, agent_id) or MethodologyAgent(id=agent_id, methodology_id=methodology.id)
        agent.code, agent.name, agent.version = code, name, data_v1.VERSION
        agent.stage_code, agent.execution_order, agent.execution_mode, agent.model_role = stage, order, mode, role
        agent.prompt_template_id = prompt_ids["final_expert" if stage == "final" else "thematic"]
        agent.input_schema_code = "rule_result_package" if stage == "final" else "graduation_thesis_context"
        agent.output_schema_code = "rule_based_final_output" if stage == "final" else "rule_based_agent_output"
        agent.is_active, agent.is_required, agent.source, agent.is_demo = True, True, data_v1.SOURCE, False
        agent.configuration = {"criteria": criteria.split(",")}
        session.add(agent)
    await session.commit(); await session.refresh(methodology)
    return methodology

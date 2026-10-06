from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate, WorkType
from app.methodology.registry import WORK_TYPE_BY_CODE
from app.methodology.seeds.candidate_dissertation import data_v1


async def ensure_candidate_dissertation_seed(session: AsyncSession) -> Methodology:
    definition = WORK_TYPE_BY_CODE["CANDIDATE_DISSERTATION"]
    work_type = await session.get(WorkType, definition.code)
    if work_type is None:
        work_type = WorkType(code=definition.code)
    work_type.display_name = definition.display_name
    work_type.description = "Предварительный анализ кандидатской диссертации по методическим рекомендациям Финансового университета."
    work_type.status = "AVAILABLE"
    work_type.sort_order = definition.sort_order
    work_type.configuration = {}
    session.add(work_type)
    await session.flush()

    existing = (
        await session.execute(
            select(Methodology).where(
                Methodology.code == "CANDIDATE_DISSERTATION",
                Methodology.version == data_v1.METHODOLOGY_VERSION,
            )
        )
    ).scalar_one_or_none()
    methodology = existing or Methodology(id=data_v1.METHODOLOGY_ID, code="CANDIDATE_DISSERTATION")
    methodology.work_type_code = "CANDIDATE_DISSERTATION"
    methodology.name = "Кандидатская диссертация"
    methodology.description = "Предварительная проверка структуры, научного аппарата, связности и оформления кандидатской диссертации."
    methodology.version = data_v1.METHODOLOGY_VERSION
    methodology.is_active = True
    methodology.is_demo = False
    methodology.source = data_v1.SOURCE
    methodology.status = "ACTIVE"
    methodology.max_score = 70
    methodology.applicable_formats = ["pdf", "docx"]
    methodology.configuration = {
        "execution_profile": "candidate_dissertation",
        "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 70},
        "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
        "evidence_rules": {"validate_quotes": True, "fields": ["quote", "page", "section", "block_index"]},
        "report_configuration": {"title": "Предварительный анализ кандидатской диссертации", "disclaimer": data_v1.DISCLAIMER},
    }
    session.add(methodology)
    await session.flush()

    prompt_ids = {}
    for item in data_v1.PROMPTS:
        prompt = await session.get(PromptTemplate, item["id"])
        if prompt is None:
            prompt = PromptTemplate(id=item["id"], methodology_id=methodology.id)
        prompt.stage = item["stage"]
        prompt.system_prompt = item["system_prompt"]
        prompt.user_template = item["user_template"]
        prompt.version = item["version"]
        prompt.is_demo = False
        prompt.source = data_v1.SOURCE
        session.add(prompt)
        prompt_ids[item["stage"]] = prompt.id

    for criterion_data in data_v1.CRITERIA:
        criterion_id = f"candidate-1-0-{criterion_data['number'].lower()}"
        criterion = await session.get(MethodologyCriterion, criterion_id)
        if criterion is None:
            criterion = MethodologyCriterion(id=criterion_id, methodology_id=methodology.id)
        criterion.number = criterion_data["number"]
        criterion.title = criterion_data["title"]
        criterion.description = criterion_data["description"]
        criterion.weight = None
        criterion.max_score = 10
        criterion.required = True
        criterion.configuration = {"score_from": "checked_applicable_rules"}
        criterion.order_index = criterion_data["order_index"]
        criterion.is_demo = False
        criterion.source = data_v1.SOURCE
        criterion.version = data_v1.VERSION
        session.add(criterion)
        for order_index, rule_data in enumerate(criterion_data["rules"], start=1):
            indicator = await session.get(MethodologyIndicator, rule_data["id"])
            if indicator is None:
                indicator = MethodologyIndicator(id=rule_data["id"], criterion_id=criterion.id)
            indicator.title = rule_data["title"]
            indicator.description = rule_data["description"]
            indicator.expected_result = rule_data["expected_result"]
            indicator.weight = rule_data["configuration"]["score_weight"]
            indicator.order_index = order_index
            indicator.required = rule_data["configuration"]["normative_strength"] == "REQUIRED"
            indicator.configuration = {"rule_code": rule_data["code"], **rule_data["configuration"]}
            indicator.is_demo = False
            indicator.source = data_v1.SOURCE
            indicator.version = data_v1.VERSION
            session.add(indicator)

    for agent_id, code, name, stage, order, mode, role, criteria in data_v1.AGENTS:
        agent = await session.get(MethodologyAgent, agent_id)
        if agent is None:
            agent = MethodologyAgent(id=agent_id, methodology_id=methodology.id)
        agent.code = code
        agent.name = name
        agent.version = data_v1.VERSION
        agent.stage_code = stage
        agent.execution_order = order
        agent.execution_mode = mode
        agent.model_role = role
        agent.prompt_template_id = prompt_ids["final_expert" if stage == "final" else "thematic"]
        agent.input_schema_code = "candidate_context" if stage != "final" else "candidate_result_package"
        agent.output_schema_code = "candidate_agent_output" if stage != "final" else "candidate_final_output"
        agent.is_active = True
        agent.is_required = True
        agent.source = data_v1.SOURCE
        agent.is_demo = False
        agent.configuration = {"criteria": criteria.split(",")}
        session.add(agent)

    await session.commit()
    await session.refresh(methodology)
    return methodology

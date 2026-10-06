from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate, WorkType
from app.methodology.registry import WORK_TYPE_BY_CODE
from app.methodology.seeds.scientific_article import data_v1


async def ensure_scientific_article_seed(session: AsyncSession) -> Methodology:
    definition = WORK_TYPE_BY_CODE["SCIENTIFIC_ARTICLE"]
    work_type = await session.get(WorkType, definition.code) or WorkType(code=definition.code)
    work_type.display_name = definition.display_name
    work_type.description = "Предварительный анализ научной статьи по внутренней методологии Digital Mentor."
    work_type.status = "AVAILABLE"
    work_type.sort_order = definition.sort_order
    work_type.configuration = {}
    session.add(work_type)
    await session.flush()

    methodology = (await session.execute(select(Methodology).where(
        Methodology.code == "SCIENTIFIC_ARTICLE", Methodology.version == data_v1.METHODOLOGY_VERSION
    ))).scalar_one_or_none() or Methodology(id=data_v1.METHODOLOGY_ID, code="SCIENTIFIC_ARTICLE")
    methodology.work_type_code = "SCIENTIFIC_ARTICLE"
    methodology.name = "Научная статья"
    methodology.description = "Внутренняя методология предварительного анализа научной статьи Digital Mentor."
    methodology.version = data_v1.METHODOLOGY_VERSION
    methodology.is_active = True
    methodology.is_demo = False
    methodology.source = data_v1.SOURCE
    methodology.status = "ACTIVE"
    methodology.max_score = 60
    methodology.applicable_formats = ["pdf", "docx"]
    methodology.configuration = {
        "execution_profile": "scientific_article", "source_type": data_v1.SOURCE_TYPE,
        "methodology_owner": "Digital Mentor", "is_official": False, "authority": None,
        "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 60},
        "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
        "evidence_rules": {"validate_quotes": True, "allow_verified_absence": True},
        "limitations": data_v1.LIMITATIONS,
        "report_configuration": {"title": "Предварительный анализ научной статьи", "disclaimer": data_v1.DISCLAIMER},
    }
    session.add(methodology)
    await session.flush()

    prompt_ids = {}
    for item in data_v1.PROMPTS:
        prompt = await session.get(PromptTemplate, item["id"]) or PromptTemplate(id=item["id"], methodology_id=methodology.id)
        prompt.stage, prompt.system_prompt, prompt.user_template = item["stage"], item["system_prompt"], item["user_template"]
        prompt.version, prompt.is_demo, prompt.source = item["version"], False, data_v1.SOURCE
        session.add(prompt)
        prompt_ids[item["stage"]] = prompt.id

    for criterion_data in data_v1.CRITERIA:
        criterion_id = f"scientific-article-1-0-{criterion_data['number'].lower()}"
        criterion = await session.get(MethodologyCriterion, criterion_id) or MethodologyCriterion(id=criterion_id, methodology_id=methodology.id)
        criterion.number, criterion.title, criterion.description = criterion_data["number"], criterion_data["title"], criterion_data["description"]
        criterion.weight, criterion.max_score, criterion.required = None, 10, True
        criterion.configuration, criterion.order_index = {"score_from": "checked_applicable_rules"}, criterion_data["order_index"]
        criterion.is_demo, criterion.source, criterion.version = False, data_v1.SOURCE, data_v1.VERSION
        session.add(criterion)
        for order_index, rule_data in enumerate(criterion_data["rules"], 1):
            indicator = await session.get(MethodologyIndicator, rule_data["id"]) or MethodologyIndicator(id=rule_data["id"], criterion_id=criterion.id)
            indicator.title, indicator.description, indicator.expected_result = rule_data["title"], rule_data["description"], rule_data["expected_result"]
            indicator.weight, indicator.order_index = rule_data["configuration"]["score_weight"], order_index
            indicator.required = rule_data["configuration"]["normative_strength"] == "REQUIRED"
            indicator.configuration = {"rule_code": rule_data["code"], **rule_data["configuration"]}
            indicator.is_demo, indicator.source, indicator.version = False, data_v1.SOURCE, data_v1.VERSION
            session.add(indicator)

    for agent_id, code, name, stage, order, mode, role, criteria in data_v1.AGENTS:
        agent = await session.get(MethodologyAgent, agent_id) or MethodologyAgent(id=agent_id, methodology_id=methodology.id)
        agent.code, agent.name, agent.version = code, name, data_v1.VERSION
        agent.stage_code, agent.execution_order, agent.execution_mode, agent.model_role = stage, order, mode, role
        agent.prompt_template_id = prompt_ids["final_expert" if stage == "final" else "thematic"]
        agent.input_schema_code = "rule_result_package" if stage == "final" else "scientific_article_context"
        agent.output_schema_code = "rule_based_final_output" if stage == "final" else "rule_based_agent_output"
        agent.is_active, agent.is_required, agent.source, agent.is_demo = True, True, data_v1.SOURCE, False
        agent.configuration = {"criteria": criteria.split(",")}
        session.add(agent)
    await session.commit()
    await session.refresh(methodology)
    return methodology

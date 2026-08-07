from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate
from app.methodology.seeds.startup_vkr.data import AGENTS, CRITERIA, METHODOLOGY_ID, METHODOLOGY_VERSION, PROMPTS, SOURCE, VERSION


async def ensure_startup_vkr_seed(session: AsyncSession) -> Methodology:
    methodology = (
        await session.execute(select(Methodology).where(Methodology.code == "STARTUP_VKR", Methodology.version == METHODOLOGY_VERSION).limit(1))
    ).scalar_one_or_none()
    if methodology is None:
        methodology = Methodology(id=METHODOLOGY_ID, code="STARTUP_VKR")
    methodology.name = "ВКР как стартап"
    methodology.version = METHODOLOGY_VERSION
    methodology.description = "Методология проверки ВКР как проектного обоснования стартапа по Анти-Дюринг: method 1.26, implementation 1.10."
    methodology.is_active = True
    methodology.is_demo = False
    methodology.source = SOURCE
    session.add(methodology)

    for prompt_data in PROMPTS:
        prompt = await session.get(PromptTemplate, prompt_data["id"])
        if prompt is None:
            prompt = PromptTemplate(id=prompt_data["id"], methodology_id=methodology.id)
        prompt.stage = prompt_data["stage"]
        prompt.system_prompt = prompt_data["system_prompt"]
        prompt.user_template = prompt_data["user_template"]
        prompt.version = VERSION
        prompt.is_demo = False
        prompt.source = SOURCE
        session.add(prompt)

    for criterion_data in CRITERIA:
        criterion = await session.get(MethodologyCriterion, criterion_data["id"])
        if criterion is None:
            criterion = MethodologyCriterion(id=criterion_data["id"], methodology_id=methodology.id)
        criterion.number = criterion_data["number"]
        criterion.title = criterion_data["title"]
        criterion.description = criterion_data["description"]
        criterion.weight = None
        criterion.order_index = criterion_data["order_index"]
        criterion.is_demo = False
        criterion.source = SOURCE
        criterion.version = VERSION
        session.add(criterion)
        for indicator_data in criterion_data["indicators"]:
            indicator = await session.get(MethodologyIndicator, indicator_data["id"])
            if indicator is None:
                indicator = MethodologyIndicator(id=indicator_data["id"], criterion_id=criterion.id)
            indicator.title = indicator_data["title"]
            indicator.description = indicator_data["description"]
            indicator.expected_result = indicator_data["expected_result"]
            indicator.weight = None
            indicator.order_index = indicator_data["order_index"]
            indicator.required = True
            indicator.is_demo = False
            indicator.source = SOURCE
            indicator.version = VERSION
            session.add(indicator)

    for agent_data in AGENTS:
        (
            agent_id,
            code,
            name,
            stage_code,
            execution_order,
            execution_mode,
            model_role,
            prompt_template_id,
            input_schema_code,
            output_schema_code,
        ) = agent_data
        agent = await session.get(MethodologyAgent, agent_id)
        if agent is None:
            agent = MethodologyAgent(id=agent_id, methodology_id=methodology.id)
        agent.code = code
        agent.name = name
        agent.version = VERSION
        agent.stage_code = stage_code
        agent.execution_order = execution_order
        agent.execution_mode = execution_mode
        agent.model_role = model_role
        agent.prompt_template_id = prompt_template_id
        agent.input_schema_code = input_schema_code
        agent.output_schema_code = output_schema_code
        agent.is_active = True
        agent.is_required = True
        agent.is_demo = False
        agent.source = SOURCE
        session.add(agent)

    await session.commit()
    await session.refresh(methodology)
    return methodology

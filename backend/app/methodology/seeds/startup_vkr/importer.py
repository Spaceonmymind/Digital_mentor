from types import ModuleType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate, WorkType
from app.methodology.registry import WORK_TYPE_BY_CODE
from app.methodology.seeds.startup_vkr import data as legacy_data
from app.methodology.seeds.startup_vkr import data_v2


async def ensure_startup_vkr_seed(session: AsyncSession) -> Methodology:
    definition = WORK_TYPE_BY_CODE["STARTUP_VKR"]
    work_type = await session.get(WorkType, definition.code)
    if work_type is None:
        work_type = WorkType(code=definition.code)
    work_type.display_name = definition.display_name
    work_type.description = definition.description
    work_type.status = "AVAILABLE"
    work_type.sort_order = definition.sort_order
    work_type.configuration = {}
    session.add(work_type)
    await session.flush()
    existing_versions = (
        await session.execute(select(Methodology).where(Methodology.code == "STARTUP_VKR"))
    ).scalars().all()
    for existing in existing_versions:
        existing.is_active = False
        session.add(existing)
    await _upsert_version(session, legacy_data, active=False)
    methodology = await _upsert_version(session, data_v2, active=True)
    await session.commit()
    await session.refresh(methodology)
    return methodology


async def _upsert_version(session: AsyncSession, data: ModuleType, *, active: bool) -> Methodology:
    methodology = (
        await session.execute(
            select(Methodology).where(
                Methodology.code == "STARTUP_VKR",
                Methodology.version == data.METHODOLOGY_VERSION,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if methodology is None:
        methodology = Methodology(id=data.METHODOLOGY_ID, code="STARTUP_VKR")
    methodology.name = "ВКР как стартап"
    methodology.work_type_code = "STARTUP_VKR"
    methodology.version = data.METHODOLOGY_VERSION
    methodology.description = (
        "Методология анализа документа ВКР в виде стартап-проекта по регламенту Финансового университета."
        if data.METHODOLOGY_VERSION == "2.0"
        else "Методология проверки ВКР как проектного обоснования стартапа по Анти-Дюринг."
    )
    methodology.is_active = active
    methodology.is_demo = False
    methodology.source = data.SOURCE
    methodology.status = "ACTIVE" if active else "INACTIVE"
    methodology.max_score = 60 if data.METHODOLOGY_VERSION == "2.0" else None
    methodology.applicable_formats = ["pdf", "docx"]
    methodology.configuration = {
        "execution_profile": "startup_vkr",
        "structure_rules": {"source": "methodology_indicators"},
        "scoring_rules": {"type": "sum", "criterion_max_score": 10},
        "evidence_rules": {"validate_quotes": True, "fields": ["quote", "page", "section", "block_index"]},
        "recommendation_rules": {"source": "versioned_prompt_templates"},
        "report_configuration": {"show_criteria": True, "score_scale": "sum"},
    }
    session.add(methodology)

    for prompt_data in data.PROMPTS:
        prompt = await session.get(PromptTemplate, prompt_data["id"])
        if prompt is None:
            prompt = PromptTemplate(id=prompt_data["id"], methodology_id=methodology.id)
        prompt.stage = prompt_data["stage"]
        prompt.system_prompt = prompt_data["system_prompt"]
        prompt.user_template = prompt_data["user_template"]
        prompt.version = data.VERSION
        prompt.is_demo = False
        prompt.source = data.SOURCE
        session.add(prompt)

    for criterion_data in data.CRITERIA:
        criterion = await session.get(MethodologyCriterion, criterion_data["id"])
        if criterion is None:
            criterion = MethodologyCriterion(id=criterion_data["id"], methodology_id=methodology.id)
        criterion.number = criterion_data["number"]
        criterion.title = criterion_data["title"]
        criterion.description = criterion_data["description"]
        criterion.weight = None
        criterion.max_score = 10 if data.METHODOLOGY_VERSION == "2.0" else None
        criterion.required = True
        criterion.configuration = {
            "evaluation_instruction": criterion_data["description"],
            "positive_indicators": [
                item[3] if isinstance(item, tuple) else item.get("expected_result")
                for item in criterion_data["indicators"]
            ],
            "negative_indicators": [],
            "evidence_requirements": ["quote", "section"],
            "critical_issues": [],
        }
        criterion.order_index = criterion_data["order_index"]
        criterion.is_demo = False
        criterion.source = data.SOURCE
        criterion.version = data.VERSION
        session.add(criterion)
        for order_index, raw_indicator in enumerate(criterion_data["indicators"], start=1):
            if isinstance(raw_indicator, tuple):
                suffix, title, description, expected_result = raw_indicator
                indicator_data = {
                    "id": f"{criterion_data['id']}-{suffix}",
                    "title": title,
                    "description": description,
                    "expected_result": expected_result,
                    "order_index": order_index,
                }
            else:
                indicator_data = raw_indicator
            indicator = await session.get(MethodologyIndicator, indicator_data["id"])
            if indicator is None:
                indicator = MethodologyIndicator(id=indicator_data["id"], criterion_id=criterion.id)
            indicator.title = indicator_data["title"]
            indicator.description = indicator_data["description"]
            indicator.expected_result = indicator_data["expected_result"]
            indicator.weight = None
            indicator.order_index = indicator_data["order_index"]
            indicator.required = True
            indicator.configuration = {}
            indicator.is_demo = False
            indicator.source = data.SOURCE
            indicator.version = data.VERSION
            session.add(indicator)

    for agent_data in data.AGENTS:
        (
            agent_id, code, name, stage_code, execution_order, execution_mode,
            model_role, prompt_template_id, input_schema_code, output_schema_code,
        ) = agent_data
        agent = await session.get(MethodologyAgent, agent_id)
        if agent is None:
            agent = MethodologyAgent(id=agent_id, methodology_id=methodology.id)
        agent.code = code
        agent.name = name
        agent.version = data.VERSION
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
        agent.configuration = getattr(data, "AGENT_CONFIGURATIONS", {}).get(code, {})
        agent.source = data.SOURCE
        session.add(agent)

    return methodology

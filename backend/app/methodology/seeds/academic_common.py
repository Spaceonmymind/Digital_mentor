from sqlalchemy import select

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate, WorkType
from app.methodology.registry import WORK_TYPE_BY_CODE


def internal_rule(prefix, index, title, strength="REQUIRED", applicability="always", capability="TEXT"):
    code = f"{prefix}.R{index:02d}"
    return {"id": f"{prefix.lower()}-1-0-r{index:02d}", "code": code, "title": title,
        "description": title, "expected_result": title,
        "configuration": {"capability": capability, "source_type": "INTERNAL_METHODOLOGY",
            "source_document": None, "source_section": None, "source_pages": [],
            "methodology_owner": "Digital Mentor", "methodology_version": "1.0", "is_official": False,
            "authority": None, "normative_strength": strength, "applicability": applicability,
            "evidence_requirements": ["quote", "section", "block_index"], "score_weight": 1.0}}


def normative_rule(prefix, index, title, section, pages, strength="REQUIRED", applicability="always", capability="TEXT"):
    item = internal_rule(prefix, index, title, strength, applicability, capability)
    item["configuration"].update({"source_type": "NORMATIVE_DOCUMENT",
        "source_document": "Оформление текста рукописи диссертации и автореферата диссертации. Методические рекомендации Финансового университета, 02.09.2022",
        "source_section": section, "source_pages": pages, "methodology_owner": "Финансовый университет",
        "is_official": True, "authority": "Финансовый университет при Правительстве Российской Федерации"})
    return item


async def ensure_academic_seed(session, data):
    definition = WORK_TYPE_BY_CODE[data.WORK_TYPE]
    wt = await session.get(WorkType, definition.code) or WorkType(code=definition.code)
    wt.display_name, wt.sort_order, wt.description, wt.status, wt.configuration = definition.display_name, definition.sort_order, data.DESCRIPTION, "AVAILABLE", {}
    session.add(wt); await session.flush()
    methodology = (await session.execute(select(Methodology).where(Methodology.code == data.CODE, Methodology.version == "1.0"))).scalar_one_or_none()
    methodology = methodology or Methodology(id=data.METHODOLOGY_ID, code=data.CODE)
    methodology.work_type_code, methodology.name, methodology.description = data.WORK_TYPE, data.NAME, data.DESCRIPTION
    methodology.version, methodology.is_active, methodology.is_demo = "1.0", True, False
    methodology.source, methodology.status, methodology.max_score = data.SOURCE, "ACTIVE", data.MAX_SCORE
    methodology.applicable_formats = ["pdf", "docx"]
    methodology.configuration = {"execution_profile": data.PROFILE, "source_type": data.SOURCE_TYPE,
        "methodology_owner": "Digital Mentor", "is_official": data.IS_OFFICIAL, "authority": data.AUTHORITY,
        "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": data.MAX_SCORE},
        "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
        "evidence_rules": {"validate_quotes": True, "allow_verified_absence": True}, "limitations": data.LIMITATIONS,
        "report_configuration": {"title": data.REPORT_TITLE, "disclaimer": data.DISCLAIMER,
            "optional_result_title": data.RESULT_TITLE}}
    session.add(methodology); await session.flush()
    prompt_ids = {}
    for item in data.PROMPTS:
        prompt = await session.get(PromptTemplate, item["id"]) or PromptTemplate(id=item["id"], methodology_id=methodology.id)
        prompt.stage, prompt.system_prompt, prompt.user_template = item["stage"], item["system_prompt"], item["user_template"]
        prompt.version, prompt.is_demo, prompt.source = item["version"], False, data.SOURCE
        session.add(prompt); prompt_ids[item["stage"]] = prompt.id
    for item in data.CRITERIA:
        cid = f"{data.SLUG}-1-0-{item['number'].lower()}"
        criterion = await session.get(MethodologyCriterion, cid) or MethodologyCriterion(id=cid, methodology_id=methodology.id)
        criterion.number, criterion.title, criterion.description = item["number"], item["title"], item["description"]
        criterion.weight, criterion.max_score, criterion.required = None, 10, True
        criterion.configuration, criterion.order_index = {"score_from": "checked_applicable_rules"}, item["order_index"]
        criterion.is_demo, criterion.source, criterion.version = False, data.SOURCE, data.VERSION
        session.add(criterion)
        for order, rule in enumerate(item["rules"], 1):
            indicator = await session.get(MethodologyIndicator, rule["id"]) or MethodologyIndicator(id=rule["id"], criterion_id=criterion.id)
            indicator.title, indicator.description, indicator.expected_result = rule["title"], rule["description"], rule["expected_result"]
            indicator.weight, indicator.order_index = 1.0, order
            indicator.required = rule["configuration"]["normative_strength"] == "REQUIRED"
            indicator.configuration = {"rule_code": rule["code"], **rule["configuration"]}
            indicator.is_demo, indicator.source, indicator.version = False, data.SOURCE, data.VERSION
            session.add(indicator)
    for aid, code, name, stage, order, mode, role, assigned in data.AGENTS:
        agent = await session.get(MethodologyAgent, aid) or MethodologyAgent(id=aid, methodology_id=methodology.id)
        agent.code, agent.name, agent.version = code, name, data.VERSION
        agent.stage_code, agent.execution_order, agent.execution_mode, agent.model_role = stage, order, mode, role
        agent.prompt_template_id = prompt_ids["final_expert" if stage == "final" else "thematic"]
        agent.input_schema_code = "rule_result_package" if stage == "final" else f"{data.PROFILE}_context"
        agent.output_schema_code = "rule_based_final_output" if stage == "final" else "rule_based_agent_output"
        agent.is_active, agent.is_required, agent.source, agent.is_demo = True, True, data.SOURCE, False
        agent.configuration = {"criteria": assigned.split(",")}; session.add(agent)
    await session.commit(); await session.refresh(methodology)
    return methodology

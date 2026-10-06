"""Register Scientific Article 1.0.

Revision ID: 0013_scientific_article_1_0
Revises: 0012_indicator_configuration
"""

from alembic import op
import sqlalchemy as sa

from app.methodology.seeds.scientific_article import data_v1


revision = "0013_scientific_article_1_0"
down_revision = "0012_indicator_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("update work_types set status='AVAILABLE', description=:description where code='SCIENTIFIC_ARTICLE'"),
                 {"description": "Предварительный анализ научной статьи по внутренней методологии Digital Mentor."})
    methodologies = sa.table("methodologies", *[sa.column(name, sa.JSON if name in {"applicable_formats", "configuration"} else None) for name in (
        "id", "work_type_code", "code", "name", "description", "version", "is_active", "is_demo", "source", "status", "max_score", "applicable_formats", "configuration")])
    bind.execute(methodologies.insert().values(
        id=data_v1.METHODOLOGY_ID, work_type_code="SCIENTIFIC_ARTICLE", code="SCIENTIFIC_ARTICLE", name="Научная статья",
        description="Внутренняя методология предварительного анализа научной статьи Digital Mentor.", version="1.0",
        is_active=True, is_demo=False, source=data_v1.SOURCE, status="ACTIVE", max_score=60, applicable_formats=["pdf", "docx"],
        configuration={"execution_profile": "scientific_article", "source_type": data_v1.SOURCE_TYPE,
                       "methodology_owner": "Digital Mentor", "is_official": False, "authority": None,
                       "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 60},
                       "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
                       "evidence_rules": {"validate_quotes": True, "allow_verified_absence": True},
                       "limitations": data_v1.LIMITATIONS,
                       "report_configuration": {"title": "Предварительный анализ научной статьи", "disclaimer": data_v1.DISCLAIMER}},
    ))
    prompts = sa.table("prompt_templates", *[sa.column(name) for name in ("id", "methodology_id", "stage", "system_prompt", "user_template", "version", "is_demo", "source")])
    bind.execute(prompts.insert(), [{"id": item["id"], "methodology_id": data_v1.METHODOLOGY_ID, "stage": item["stage"],
        "system_prompt": item["system_prompt"], "user_template": item["user_template"], "version": item["version"],
        "is_demo": False, "source": data_v1.SOURCE} for item in data_v1.PROMPTS])
    criteria_table = sa.table("methodology_criteria", *[sa.column(name, sa.JSON if name == "configuration" else None) for name in
        ("id", "methodology_id", "number", "title", "description", "weight", "max_score", "required", "configuration", "order_index", "is_demo", "source", "version")])
    indicators = sa.table("methodology_indicators", *[sa.column(name, sa.JSON if name == "configuration" else None) for name in
        ("id", "criterion_id", "title", "description", "expected_result", "weight", "order_index", "required", "configuration", "is_demo", "source", "version")])
    for criterion in data_v1.CRITERIA:
        criterion_id = f"scientific-article-1-0-{criterion['number'].lower()}"
        bind.execute(criteria_table.insert().values(id=criterion_id, methodology_id=data_v1.METHODOLOGY_ID,
            number=criterion["number"], title=criterion["title"], description=criterion["description"], weight=None,
            max_score=10, required=True, configuration={"score_from": "checked_applicable_rules"},
            order_index=criterion["order_index"], is_demo=False, source=data_v1.SOURCE, version=data_v1.VERSION))
        bind.execute(indicators.insert(), [{"id": item["id"], "criterion_id": criterion_id, "title": item["title"],
            "description": item["description"], "expected_result": item["expected_result"],
            "weight": item["configuration"]["score_weight"], "order_index": index,
            "required": item["configuration"]["normative_strength"] == "REQUIRED",
            "configuration": {"rule_code": item["code"], **item["configuration"]}, "is_demo": False,
            "source": data_v1.SOURCE, "version": data_v1.VERSION} for index, item in enumerate(criterion["rules"], 1)])
    agents = sa.table("methodology_agents", *[sa.column(name, sa.JSON if name == "configuration" else None) for name in
        ("id", "methodology_id", "code", "name", "version", "stage_code", "execution_order", "execution_mode", "model_role", "prompt_template_id", "input_schema_code", "output_schema_code", "is_active", "is_required", "source", "is_demo", "configuration")])
    bind.execute(agents.insert(), [{"id": agent_id, "methodology_id": data_v1.METHODOLOGY_ID, "code": code,
        "name": name, "version": data_v1.VERSION, "stage_code": stage, "execution_order": order,
        "execution_mode": mode, "model_role": role,
        "prompt_template_id": "scientific-article-1-0-final-prompt" if stage == "final" else "scientific-article-1-0-thematic-prompt",
        "input_schema_code": "rule_result_package" if stage == "final" else "scientific_article_context",
        "output_schema_code": "rule_based_final_output" if stage == "final" else "rule_based_agent_output",
        "is_active": True, "is_required": True, "source": data_v1.SOURCE, "is_demo": False,
        "configuration": {"criteria": criteria.split(",")}} for agent_id, code, name, stage, order, mode, role, criteria in data_v1.AGENTS])


def downgrade() -> None:
    bind = op.get_bind()
    params = {"id": data_v1.METHODOLOGY_ID}
    bind.execute(sa.text("delete from methodology_agents where methodology_id=:id"), params)
    bind.execute(sa.text("delete from prompt_templates where methodology_id=:id"), params)
    bind.execute(sa.text("delete from methodology_indicators where criterion_id in (select id from methodology_criteria where methodology_id=:id)"), params)
    bind.execute(sa.text("delete from methodology_criteria where methodology_id=:id"), params)
    bind.execute(sa.text("delete from methodologies where id=:id"), params)
    bind.execute(sa.text("update work_types set status='NOT_CONFIGURED', description='Методология находится в подготовке.' where code='SCIENTIFIC_ARTICLE'"))

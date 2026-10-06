"""Register Graduation Thesis 1.0.

Revision ID: 0014_graduation_thesis_1_0
Revises: 0013_scientific_article_1_0
"""
from alembic import op
import sqlalchemy as sa
from app.methodology.seeds.graduation_thesis import data_v1

revision = "0014_graduation_thesis_1_0"
down_revision = "0013_scientific_article_1_0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("update work_types set status='AVAILABLE', description=:d where code='BACHELOR_SPECIALIST_THESIS'"),
                 {"d": "Предварительный анализ ВКР бакалавра или специалиста по внутренней методологии Digital Mentor."})
    methodologies = sa.table("methodologies", *[sa.column(n, sa.JSON if n in {"applicable_formats", "configuration"} else None) for n in
        ("id", "work_type_code", "code", "name", "description", "version", "is_active", "is_demo", "source", "status", "max_score", "applicable_formats", "configuration")])
    bind.execute(methodologies.insert().values(id=data_v1.METHODOLOGY_ID, work_type_code="BACHELOR_SPECIALIST_THESIS",
        code="GRADUATION_THESIS", name="ВКР бакалавра / специалиста",
        description="Внутренняя методология предварительного анализа выпускной квалификационной работы Digital Mentor.",
        version="1.0", is_active=True, is_demo=False, source=data_v1.SOURCE, status="ACTIVE", max_score=60,
        applicable_formats=["pdf", "docx"], configuration={"execution_profile": "graduation_thesis",
            "source_type": data_v1.SOURCE_TYPE, "methodology_owner": "Digital Mentor", "is_official": False, "authority": None,
            "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 60},
            "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
            "evidence_rules": {"validate_quotes": True, "allow_verified_absence": True}, "limitations": data_v1.LIMITATIONS,
            "report_configuration": {"title": "Предварительный анализ выпускной квалификационной работы", "disclaimer": data_v1.DISCLAIMER}}))
    prompts = sa.table("prompt_templates", *[sa.column(n) for n in ("id", "methodology_id", "stage", "system_prompt", "user_template", "version", "is_demo", "source")])
    bind.execute(prompts.insert(), [{"id": x["id"], "methodology_id": data_v1.METHODOLOGY_ID, "stage": x["stage"],
        "system_prompt": x["system_prompt"], "user_template": x["user_template"], "version": x["version"], "is_demo": False,
        "source": data_v1.SOURCE} for x in data_v1.PROMPTS])
    criteria = sa.table("methodology_criteria", *[sa.column(n, sa.JSON if n == "configuration" else None) for n in
        ("id", "methodology_id", "number", "title", "description", "weight", "max_score", "required", "configuration", "order_index", "is_demo", "source", "version")])
    indicators = sa.table("methodology_indicators", *[sa.column(n, sa.JSON if n == "configuration" else None) for n in
        ("id", "criterion_id", "title", "description", "expected_result", "weight", "order_index", "required", "configuration", "is_demo", "source", "version")])
    for item in data_v1.CRITERIA:
        cid = f"graduation-thesis-1-0-{item['number'].lower()}"
        bind.execute(criteria.insert().values(id=cid, methodology_id=data_v1.METHODOLOGY_ID, number=item["number"],
            title=item["title"], description=item["description"], weight=None, max_score=10, required=True,
            configuration={"score_from": "checked_applicable_rules"}, order_index=item["order_index"], is_demo=False,
            source=data_v1.SOURCE, version=data_v1.VERSION))
        bind.execute(indicators.insert(), [{"id": r["id"], "criterion_id": cid, "title": r["title"],
            "description": r["description"], "expected_result": r["expected_result"], "weight": 1.0, "order_index": i,
            "required": r["configuration"]["normative_strength"] == "REQUIRED",
            "configuration": {"rule_code": r["code"], **r["configuration"]}, "is_demo": False,
            "source": data_v1.SOURCE, "version": data_v1.VERSION} for i, r in enumerate(item["rules"], 1)])
    agents = sa.table("methodology_agents", *[sa.column(n, sa.JSON if n == "configuration" else None) for n in
        ("id", "methodology_id", "code", "name", "version", "stage_code", "execution_order", "execution_mode", "model_role", "prompt_template_id", "input_schema_code", "output_schema_code", "is_active", "is_required", "source", "is_demo", "configuration")])
    bind.execute(agents.insert(), [{"id": aid, "methodology_id": data_v1.METHODOLOGY_ID, "code": code, "name": name,
        "version": data_v1.VERSION, "stage_code": stage, "execution_order": order, "execution_mode": mode,
        "model_role": role, "prompt_template_id": "graduation-thesis-1-0-final-prompt" if stage == "final" else "graduation-thesis-1-0-thematic-prompt",
        "input_schema_code": "rule_result_package" if stage == "final" else "graduation_thesis_context",
        "output_schema_code": "rule_based_final_output" if stage == "final" else "rule_based_agent_output",
        "is_active": True, "is_required": True, "source": data_v1.SOURCE, "is_demo": False,
        "configuration": {"criteria": assigned.split(",")}} for aid, code, name, stage, order, mode, role, assigned in data_v1.AGENTS])


def downgrade():
    bind = op.get_bind(); p = {"id": data_v1.METHODOLOGY_ID}
    bind.execute(sa.text("delete from methodology_agents where methodology_id=:id"), p)
    bind.execute(sa.text("delete from prompt_templates where methodology_id=:id"), p)
    bind.execute(sa.text("delete from methodology_indicators where criterion_id in (select id from methodology_criteria where methodology_id=:id)"), p)
    bind.execute(sa.text("delete from methodology_criteria where methodology_id=:id"), p)
    bind.execute(sa.text("delete from methodologies where id=:id"), p)
    bind.execute(sa.text("update work_types set status='NOT_CONFIGURED', description='Методология находится в подготовке.' where code='BACHELOR_SPECIALIST_THESIS'"))

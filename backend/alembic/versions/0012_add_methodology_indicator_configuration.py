"""Add universal rule configuration to methodology indicators.

Revision ID: 0012_indicator_configuration
Revises: 0011_add_work_type_registry
"""

from alembic import op
import sqlalchemy as sa

from app.methodology.seeds.candidate_dissertation import data_v1


revision = "0012_indicator_configuration"
down_revision = "0011_add_work_type_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("methodology_indicators") as batch:
        batch.add_column(sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "update work_types set status='AVAILABLE', description=:description where code='CANDIDATE_DISSERTATION'"
        ),
        {"description": "Предварительный анализ кандидатской диссертации по методическим рекомендациям Финансового университета."},
    )
    methodologies = sa.table(
        "methodologies",
        sa.column("id"), sa.column("work_type_code"), sa.column("code"), sa.column("name"),
        sa.column("description"), sa.column("version"), sa.column("is_active"), sa.column("is_demo"),
        sa.column("source"), sa.column("status"), sa.column("max_score"), sa.column("applicable_formats", sa.JSON),
        sa.column("configuration", sa.JSON),
    )
    bind.execute(
        methodologies.insert().values(
            id=data_v1.METHODOLOGY_ID,
            work_type_code="CANDIDATE_DISSERTATION",
            code="CANDIDATE_DISSERTATION",
            name="Кандидатская диссертация",
            description="Предварительная проверка структуры, научного аппарата, связности и оформления кандидатской диссертации.",
            version="1.0", is_active=True, is_demo=False, source=data_v1.SOURCE, status="ACTIVE", max_score=70,
            applicable_formats=["pdf", "docx"],
            configuration={
                "execution_profile": "candidate_dissertation",
                "scoring_rules": {"type": "checked_applicable_rules", "criterion_max_score": 10, "nominal_max_score": 70},
                "rule_statuses": ["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"],
                "evidence_rules": {"validate_quotes": True, "fields": ["quote", "page", "section", "block_index"]},
                "report_configuration": {"title": "Предварительный анализ кандидатской диссертации", "disclaimer": data_v1.DISCLAIMER},
            },
        )
    )
    prompts = sa.table(
        "prompt_templates", sa.column("id"), sa.column("methodology_id"), sa.column("stage"),
        sa.column("system_prompt"), sa.column("user_template"), sa.column("version"),
        sa.column("is_demo"), sa.column("source"),
    )
    bind.execute(prompts.insert(), [
        {
            "id": item["id"], "methodology_id": data_v1.METHODOLOGY_ID, "stage": item["stage"],
            "system_prompt": item["system_prompt"], "user_template": item["user_template"],
            "version": item["version"], "is_demo": False, "source": data_v1.SOURCE,
        }
        for item in data_v1.PROMPTS
    ])
    criteria_table = sa.table(
        "methodology_criteria", sa.column("id"), sa.column("methodology_id"), sa.column("number"),
        sa.column("title"), sa.column("description"), sa.column("weight"), sa.column("max_score"),
        sa.column("required"), sa.column("configuration", sa.JSON), sa.column("order_index"),
        sa.column("is_demo"), sa.column("source"), sa.column("version"),
    )
    indicators = sa.table(
        "methodology_indicators", sa.column("id"), sa.column("criterion_id"), sa.column("title"),
        sa.column("description"), sa.column("expected_result"), sa.column("weight"),
        sa.column("order_index"), sa.column("required"), sa.column("configuration", sa.JSON),
        sa.column("is_demo"), sa.column("source"), sa.column("version"),
    )
    for criterion in data_v1.CRITERIA:
        criterion_id = f"candidate-1-0-{criterion['number'].lower()}"
        bind.execute(criteria_table.insert().values(
            id=criterion_id, methodology_id=data_v1.METHODOLOGY_ID, number=criterion["number"],
            title=criterion["title"], description=criterion["description"], weight=None, max_score=10,
            required=True, configuration={"score_from": "checked_applicable_rules"},
            order_index=criterion["order_index"], is_demo=False, source=data_v1.SOURCE, version=data_v1.VERSION,
        ))
        bind.execute(indicators.insert(), [
            {
                "id": item["id"], "criterion_id": criterion_id, "title": item["title"],
                "description": item["description"], "expected_result": item["expected_result"],
                "weight": item["configuration"]["score_weight"], "order_index": index,
                "required": item["configuration"]["normative_strength"] == "REQUIRED",
                "configuration": {"rule_code": item["code"], **item["configuration"]},
                "is_demo": False, "source": data_v1.SOURCE, "version": data_v1.VERSION,
            }
            for index, item in enumerate(criterion["rules"], start=1)
        ])
    agents = sa.table(
        "methodology_agents", sa.column("id"), sa.column("methodology_id"), sa.column("code"),
        sa.column("name"), sa.column("version"), sa.column("stage_code"), sa.column("execution_order"),
        sa.column("execution_mode"), sa.column("model_role"), sa.column("prompt_template_id"),
        sa.column("input_schema_code"), sa.column("output_schema_code"), sa.column("is_active"),
        sa.column("is_required"), sa.column("source"), sa.column("is_demo"), sa.column("configuration", sa.JSON),
    )
    bind.execute(agents.insert(), [
        {
            "id": agent_id, "methodology_id": data_v1.METHODOLOGY_ID, "code": code, "name": name,
            "version": data_v1.VERSION, "stage_code": stage, "execution_order": order,
            "execution_mode": mode, "model_role": role,
            "prompt_template_id": "candidate-1-0-final-prompt" if stage == "final" else "candidate-1-0-thematic-prompt",
            "input_schema_code": "candidate_result_package" if stage == "final" else "candidate_context",
            "output_schema_code": "candidate_final_output" if stage == "final" else "candidate_agent_output",
            "is_active": True, "is_required": True, "source": data_v1.SOURCE, "is_demo": False,
            "configuration": {"criteria": criteria.split(",")},
        }
        for agent_id, code, name, stage, order, mode, role, criteria in data_v1.AGENTS
    ])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("delete from methodology_agents where methodology_id=:id"), {"id": data_v1.METHODOLOGY_ID})
    bind.execute(sa.text("delete from prompt_templates where methodology_id=:id"), {"id": data_v1.METHODOLOGY_ID})
    bind.execute(sa.text("delete from methodology_indicators where criterion_id in (select id from methodology_criteria where methodology_id=:id)"), {"id": data_v1.METHODOLOGY_ID})
    bind.execute(sa.text("delete from methodology_criteria where methodology_id=:id"), {"id": data_v1.METHODOLOGY_ID})
    bind.execute(sa.text("delete from methodologies where id=:id"), {"id": data_v1.METHODOLOGY_ID})
    bind.execute(sa.text("update work_types set status='NOT_CONFIGURED', description='Методология находится в подготовке.' where code='CANDIDATE_DISSERTATION'"))
    with op.batch_alter_table("methodology_indicators") as batch:
        batch.drop_column("configuration")

"""Add STARTUP_VKR 2.0 based on the FinUniversity startup-VKR regulation.

Revision ID: 0010_startup_vkr_regulation_2_0
Revises: 0009_add_detailed_reports
"""

from alembic import op
import sqlalchemy as sa

from app.methodology.seeds.startup_vkr.data_v2 import (
    AGENTS,
    CRITERIA,
    METHODOLOGY_ID,
    METHODOLOGY_VERSION,
    PROMPTS,
    SOURCE,
    VERSION,
)


revision = "0010_startup_vkr_regulation_2_0"
down_revision = "0009_add_detailed_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("update methodologies set is_active = false where code = 'STARTUP_VKR'"))
    methodology_values = {
        "id": METHODOLOGY_ID,
        "name": "ВКР как стартап",
        "description": "Анализ документа ВКР в виде стартап-проекта по регламенту Финансового университета.",
        "version": METHODOLOGY_VERSION,
        "source": SOURCE,
    }
    if bind.dialect.name == "sqlite":
        # Migration 0007 retains SQLite's historical unique(code) constraint.
        # SQLite is used for migration smoke checks only, so update its single row in place.
        methodology_id = bind.execute(
            sa.text("select id from methodologies where code = 'STARTUP_VKR' limit 1")
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                update methodologies set name=:name, description=:description, version=:version,
                    is_active=true, is_demo=false, source=:source where id=:id
                """
            ),
            {**methodology_values, "id": methodology_id},
        )
    else:
        methodology_id = METHODOLOGY_ID
        bind.execute(
            sa.text(
                """
                insert into methodologies (id, code, name, description, version, is_active, is_demo, source)
                values (:id, 'STARTUP_VKR', :name, :description, :version, true, false, :source)
                on conflict (code, version) do update set
                    name = excluded.name, description = excluded.description, is_active = true,
                    is_demo = false, source = excluded.source
                """
            ),
            methodology_values,
        )

    for prompt in PROMPTS:
        bind.execute(
            sa.text(
                """
                insert into prompt_templates (id, methodology_id, stage, system_prompt, user_template, version, is_demo, source)
                values (:id, :methodology_id, :stage, :system_prompt, :user_template, :version, false, :source)
                on conflict (methodology_id, stage, version) do update set
                    system_prompt = excluded.system_prompt,
                    user_template = excluded.user_template,
                    is_demo = false,
                    source = excluded.source
                """
            ),
            {**prompt, "methodology_id": methodology_id, "version": VERSION, "source": SOURCE},
        )

    for criterion in CRITERIA:
        bind.execute(
            sa.text(
                """
                insert into methodology_criteria
                    (id, methodology_id, number, title, description, weight, order_index, is_demo, source, version)
                values (:id, :methodology_id, :number, :title, :description, null, :order_index, false, :source, :version)
                on conflict (methodology_id, number) do update set
                    title = excluded.title, description = excluded.description,
                    order_index = excluded.order_index, source = excluded.source, version = excluded.version
                """
            ),
            {**criterion, "methodology_id": methodology_id, "source": SOURCE, "version": VERSION},
        )
        for order_index, indicator in enumerate(criterion["indicators"], start=1):
            suffix, title, description, expected_result = indicator
            bind.execute(
                sa.text(
                    """
                    insert into methodology_indicators
                        (id, criterion_id, title, description, expected_result, weight, order_index, required, is_demo, source, version)
                    values (:id, :criterion_id, :title, :description, :expected_result, null, :order_index, true, false, :source, :version)
                    on conflict (criterion_id, order_index) do update set
                        title = excluded.title, description = excluded.description, expected_result = excluded.expected_result,
                        order_index = excluded.order_index, source = excluded.source, version = excluded.version
                    """
                ),
                {
                    "id": f"{criterion['id']}-{suffix}",
                    "criterion_id": criterion["id"],
                    "title": title,
                    "description": description,
                    "expected_result": expected_result,
                    "order_index": order_index,
                    "source": SOURCE,
                    "version": VERSION,
                },
            )

    for agent in AGENTS:
        (
            agent_id, code, name, stage_code, execution_order, execution_mode,
            model_role, prompt_template_id, input_schema_code, output_schema_code,
        ) = agent
        bind.execute(
            sa.text(
                """
                insert into methodology_agents
                    (id, methodology_id, code, name, version, stage_code, execution_order,
                     execution_mode, model_role, prompt_template_id, input_schema_code,
                     output_schema_code, is_active, is_required, source, is_demo)
                values
                    (:id, :methodology_id, :code, :name, :version, :stage_code, :execution_order,
                     :execution_mode, :model_role, :prompt_template_id, :input_schema_code,
                     :output_schema_code, true, true, :source, false)
                on conflict (methodology_id, code, version) do update set
                    name = excluded.name, stage_code = excluded.stage_code,
                    execution_order = excluded.execution_order, execution_mode = excluded.execution_mode,
                    model_role = excluded.model_role, prompt_template_id = excluded.prompt_template_id,
                    input_schema_code = excluded.input_schema_code, output_schema_code = excluded.output_schema_code,
                    is_active = true, is_required = true, source = excluded.source, is_demo = false
                """
            ),
            {
                "id": agent_id,
                "methodology_id": methodology_id,
                "code": code,
                "name": name,
                "version": VERSION,
                "stage_code": stage_code,
                "execution_order": execution_order,
                "execution_mode": execution_mode,
                "model_role": model_role,
                "prompt_template_id": prompt_template_id,
                "input_schema_code": input_schema_code,
                "output_schema_code": output_schema_code,
                "source": SOURCE,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("delete from methodology_agents where version = :version"), {"version": VERSION})
        bind.execute(sa.text("delete from prompt_templates where version = :version"), {"version": VERSION})
        bind.execute(sa.text("delete from methodology_indicators where version = :version"), {"version": VERSION})
        bind.execute(sa.text("delete from methodology_criteria where version = :version"), {"version": VERSION})
        bind.execute(
            sa.text(
                "update methodologies set version='1.1', is_active=true, source='anti_during_methodology' "
                "where code='STARTUP_VKR'"
            )
        )
        return
    bind.execute(sa.text("delete from methodology_agents where methodology_id = :id"), {"id": METHODOLOGY_ID})
    bind.execute(sa.text("delete from prompt_templates where methodology_id = :id"), {"id": METHODOLOGY_ID})
    bind.execute(
        sa.text("delete from methodology_indicators where criterion_id in (select id from methodology_criteria where methodology_id = :id)"),
        {"id": METHODOLOGY_ID},
    )
    bind.execute(sa.text("delete from methodology_criteria where methodology_id = :id"), {"id": METHODOLOGY_ID})
    bind.execute(sa.text("delete from methodologies where id = :id"), {"id": METHODOLOGY_ID})
    bind.execute(sa.text("update methodologies set is_active = (version = '1.1') where code = 'STARTUP_VKR'"))

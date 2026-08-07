"""add startup vkr p112 methodology version

Revision ID: 0007_startup_vkr_p112_report
Revises: 0006_tune_startup_vkr_prompts
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa

from app.methodology.seeds.startup_vkr.data import AGENTS, CRITERIA, METHODOLOGY_ID, METHODOLOGY_VERSION, PROMPTS, SOURCE, VERSION


revision = "0007_startup_vkr_p112_report"
down_revision = "0006_tune_startup_vkr_prompts"
branch_labels = None
depends_on = None


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item["name"] == constraint_name for item in inspector.get_unique_constraints(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(item["name"] == index_name for item in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        if _constraint_exists("methodologies", "methodologies_code_key"):
            op.drop_constraint("methodologies_code_key", "methodologies", type_="unique")
        if not _constraint_exists("methodologies", "uq_methodologies_code_version"):
            op.create_unique_constraint("uq_methodologies_code_version", "methodologies", ["code", "version"])
    else:
        # SQLite is used only by local migration checks. It cannot drop the old inline
        # unique(code) constraint cheaply, so replace the demo STARTUP_VKR row.
        _delete_startup_vkr_rows(bind, "demo-methodology-startup-vkr")
        if not _index_exists("methodologies", "uq_methodologies_code_version"):
            op.create_index("uq_methodologies_code_version", "methodologies", ["code", "version"], unique=True)

    _seed_startup_vkr_1_1()


def downgrade() -> None:
    bind = op.get_bind()
    _delete_startup_vkr_rows(bind, METHODOLOGY_ID)
    if bind.dialect.name != "sqlite":
        if _constraint_exists("methodologies", "uq_methodologies_code_version"):
            op.drop_constraint("uq_methodologies_code_version", "methodologies", type_="unique")
        if not _constraint_exists("methodologies", "methodologies_code_key"):
            op.create_unique_constraint("methodologies_code_key", "methodologies", ["code"])


def _delete_startup_vkr_rows(bind, methodology_id: str) -> None:
    bind.execute(sa.text("delete from methodology_agents where methodology_id = :methodology_id"), {"methodology_id": methodology_id})
    bind.execute(sa.text("delete from prompt_templates where methodology_id = :methodology_id"), {"methodology_id": methodology_id})
    bind.execute(
        sa.text(
            """
            delete from methodology_indicators
            where criterion_id in (select id from methodology_criteria where methodology_id = :methodology_id)
            """
        ),
        {"methodology_id": methodology_id},
    )
    bind.execute(sa.text("delete from methodology_criteria where methodology_id = :methodology_id"), {"methodology_id": methodology_id})
    bind.execute(sa.text("delete from methodologies where id = :methodology_id"), {"methodology_id": methodology_id})


def _seed_startup_vkr_1_1() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            insert into methodologies (id, code, name, description, version, is_active, is_demo, source)
            values (:id, 'STARTUP_VKR', :name, :description, :version, true, false, :source)
            on conflict (code, version) do update set
                name = excluded.name,
                description = excluded.description,
                is_active = true,
                is_demo = false,
                source = excluded.source
            """
        ),
        {
            "id": METHODOLOGY_ID,
            "name": "ВКР как стартап",
            "description": "Методология проверки ВКР как проектного обоснования стартапа. Метод ред.1.26, реализация ред.1.10.",
            "version": METHODOLOGY_VERSION,
            "source": SOURCE,
        },
    )
    bind.execute(sa.text("update methodologies set is_active = true where code = 'STARTUP_VKR' and version = '1.0'"))

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
            {
                "id": prompt["id"],
                "methodology_id": METHODOLOGY_ID,
                "stage": prompt["stage"],
                "system_prompt": prompt["system_prompt"],
                "user_template": prompt["user_template"],
                "version": VERSION,
                "source": SOURCE,
            },
        )

    for criterion in CRITERIA:
        bind.execute(
            sa.text(
                """
                insert into methodology_criteria (id, methodology_id, number, title, description, weight, order_index, is_demo, source, version)
                values (:id, :methodology_id, :number, :title, :description, null, :order_index, false, :source, :version)
                on conflict (methodology_id, number) do update set
                    title = excluded.title,
                    description = excluded.description,
                    weight = null,
                    order_index = excluded.order_index,
                    is_demo = false,
                    source = excluded.source,
                    version = excluded.version
                """
            ),
            {
                "id": criterion["id"],
                "methodology_id": METHODOLOGY_ID,
                "number": criterion["number"],
                "title": criterion["title"],
                "description": criterion["description"],
                "order_index": criterion["order_index"],
                "source": SOURCE,
                "version": VERSION,
            },
        )
        for indicator in criterion["indicators"]:
            bind.execute(
                sa.text(
                    """
                    insert into methodology_indicators (
                        id, criterion_id, title, description, expected_result, weight, order_index, required, is_demo, source, version
                    )
                    values (:id, :criterion_id, :title, :description, :expected_result, null, :order_index, true, false, :source, :version)
                    on conflict (criterion_id, order_index) do update set
                        title = excluded.title,
                        description = excluded.description,
                        expected_result = excluded.expected_result,
                        weight = null,
                        required = true,
                        is_demo = false,
                        source = excluded.source,
                        version = excluded.version
                    """
                ),
                {
                    "id": indicator["id"],
                    "criterion_id": criterion["id"],
                    "title": indicator["title"],
                    "description": indicator["description"],
                    "expected_result": indicator["expected_result"],
                    "order_index": indicator["order_index"],
                    "source": SOURCE,
                    "version": VERSION,
                },
            )

    for values in AGENTS:
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
        ) = values
        bind.execute(
            sa.text(
                """
                insert into methodology_agents (
                    id, methodology_id, code, name, version, stage_code, execution_order,
                    execution_mode, model_role, prompt_template_id, input_schema_code,
                    output_schema_code, is_active, is_required, source, is_demo
                )
                values (
                    :id, :methodology_id, :code, :name, :version, :stage_code, :execution_order,
                    :execution_mode, :model_role, :prompt_template_id, :input_schema_code,
                    :output_schema_code, true, true, :source, false
                )
                on conflict (methodology_id, code, version) do update set
                    name = excluded.name,
                    stage_code = excluded.stage_code,
                    execution_order = excluded.execution_order,
                    execution_mode = excluded.execution_mode,
                    model_role = excluded.model_role,
                    prompt_template_id = excluded.prompt_template_id,
                    input_schema_code = excluded.input_schema_code,
                    output_schema_code = excluded.output_schema_code,
                    is_active = true,
                    is_required = true,
                    source = excluded.source,
                    is_demo = false
                """
            ),
            {
                "id": agent_id,
                "methodology_id": METHODOLOGY_ID,
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

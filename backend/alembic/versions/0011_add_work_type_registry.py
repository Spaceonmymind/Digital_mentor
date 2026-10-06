"""Add versioned work type and methodology registry metadata.

Revision ID: 0011_add_work_type_registry
Revises: 0010_startup_vkr_regulation_2_0
"""

from alembic import op
import sqlalchemy as sa

from app.methodology.seeds.startup_vkr.data_v2 import AGENT_CONFIGURATIONS, CRITERIA


revision = "0011_add_work_type_registry"
down_revision = "0010_startup_vkr_regulation_2_0"
branch_labels = None
depends_on = None


WORK_TYPES = (
    ("STARTUP_VKR", "ВКР в виде стартапа", "Анализ стартап-проекта по утверждённой методологии.", "AVAILABLE", 10),
    ("COURSE_WORK", "Курсовая работа", "Методология находится в подготовке.", "NOT_CONFIGURED", 20),
    ("BACHELOR_SPECIALIST_THESIS", "ВКР бакалавра / специалиста", "Методология находится в подготовке.", "NOT_CONFIGURED", 30),
    ("MASTER_THESIS", "Магистерская диссертация", "Методология находится в подготовке.", "NOT_CONFIGURED", 40),
    ("PRACTICE_REPORT", "Отчёт по практике", "Методология находится в подготовке.", "NOT_CONFIGURED", 50),
    ("RESEARCH_REPORT", "Отчёт по НИР", "Методология находится в подготовке.", "NOT_CONFIGURED", 60),
    ("SCIENTIFIC_ARTICLE", "Научная статья", "Методология находится в подготовке.", "NOT_CONFIGURED", 70),
    ("CANDIDATE_DISSERTATION", "Кандидатская диссертация", "Методология находится в подготовке.", "NOT_CONFIGURED", 80),
    ("DOCTORAL_DISSERTATION", "Докторская диссертация", "Методология находится в подготовке.", "NOT_CONFIGURED", 90),
    ("DISSERTATION_ABSTRACT", "Автореферат диссертации", "Методология находится в подготовке.", "NOT_CONFIGURED", 100),
)


def upgrade() -> None:
    op.create_table(
        "work_types",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("code"),
    )
    work_types = sa.table(
        "work_types",
        sa.column("code", sa.String),
        sa.column("display_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("status", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("configuration", sa.JSON),
    )
    op.bulk_insert(
        work_types,
        [
            {
                "code": code,
                "display_name": display_name,
                "description": description,
                "status": status,
                "sort_order": sort_order,
                "configuration": {},
            }
            for code, display_name, description, status, sort_order in WORK_TYPES
        ],
    )

    with op.batch_alter_table("methodologies") as batch:
        batch.add_column(sa.Column("work_type_code", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"))
        batch.add_column(sa.Column("max_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("applicable_formats", sa.JSON(), nullable=False, server_default=sa.text("'[\"pdf\", \"docx\"]'")))
        batch.add_column(sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_foreign_key("fk_methodologies_work_type", "work_types", ["work_type_code"], ["code"])
        batch.create_index("ix_methodologies_work_type", ["work_type_code"])

    with op.batch_alter_table("methodology_criteria") as batch:
        batch.add_column(sa.Column("max_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    with op.batch_alter_table("methodology_agents") as batch:
        batch.add_column(sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("work_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("methodology_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("methodology_max_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("methodology_parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_index("ix_analyses_work_type", ["work_type"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            update methodologies
            set work_type_code = 'STARTUP_VKR',
                status = case when is_active then 'ACTIVE' else 'INACTIVE' end,
                max_score = case when version = '2.0' then 60 else null end,
                configuration = case when version = '2.0'
                    then :configuration else configuration end
            where code = 'STARTUP_VKR'
            """
        ).bindparams(sa.bindparam("configuration", type_=sa.JSON())),
        {
            "configuration": {
                "execution_profile": "startup_vkr",
                "structure_rules": {"source": "methodology_indicators"},
                "scoring_rules": {"type": "sum", "criterion_max_score": 10},
                "evidence_rules": {"validate_quotes": True, "fields": ["quote", "page", "section", "block_index"]},
                "recommendation_rules": {"source": "versioned_prompt_templates"},
                "report_configuration": {"show_criteria": True, "score_scale": "sum"},
            }
        },
    )
    for agent_code, configuration in AGENT_CONFIGURATIONS.items():
        bind.execute(
            sa.text(
                """
                update methodology_agents
                set configuration = :configuration
                where code = :agent_code
                  and methodology_id in (
                    select id from methodologies where code = 'STARTUP_VKR' and version = '2.0'
                  )
                """
            ).bindparams(sa.bindparam("configuration", type_=sa.JSON())),
            {"configuration": configuration, "agent_code": agent_code},
        )
    bind.execute(
        sa.text(
            """
            update methodology_criteria
            set max_score = 10, required = true
            where methodology_id in (
                select id from methodologies where code = 'STARTUP_VKR' and version = '2.0'
            )
            """
        )
    )
    for criterion in CRITERIA:
        positive_indicators = [item[3] for item in criterion["indicators"]]
        configuration = {
            "evaluation_instruction": criterion["description"],
            "positive_indicators": positive_indicators,
            "negative_indicators": [],
            "evidence_requirements": ["quote", "section"],
            "critical_issues": [],
        }
        bind.execute(
            sa.text(
                """
                update methodology_criteria
                set configuration = :configuration
                where methodology_id in (
                    select id from methodologies where code = 'STARTUP_VKR' and version = '2.0'
                ) and number = :number
                """
            ).bindparams(sa.bindparam("configuration", type_=sa.JSON())),
            {"configuration": configuration, "number": criterion["number"]},
        )
    bind.execute(
        sa.text(
            """
            update analyses
            set work_type = 'STARTUP_VKR',
                methodology_name = 'ВКР как стартап',
                methodology_max_score = case when methodology_version = '2.0' then 60 else null end
            where methodology_id = 'STARTUP_VKR'
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.drop_index("ix_analyses_work_type")
        batch.drop_column("methodology_parameters")
        batch.drop_column("methodology_max_score")
        batch.drop_column("methodology_name")
        batch.drop_column("work_type")
    with op.batch_alter_table("methodology_agents") as batch:
        batch.drop_column("configuration")
    with op.batch_alter_table("methodology_criteria") as batch:
        batch.drop_column("configuration")
        batch.drop_column("required")
        batch.drop_column("max_score")
    with op.batch_alter_table("methodologies") as batch:
        batch.drop_index("ix_methodologies_work_type")
        batch.drop_constraint("fk_methodologies_work_type", type_="foreignkey")
        batch.drop_column("configuration")
        batch.drop_column("applicable_formats")
        batch.drop_column("max_score")
        batch.drop_column("status")
        batch.drop_column("work_type_code")
    op.drop_table("work_types")

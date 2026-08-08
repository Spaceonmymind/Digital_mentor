"""add assessment execution persistence

Revision ID: 0004_add_assessment_execution
Revises: 0003_add_methodology_domain
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_assessment_execution"
down_revision = "0003_add_methodology_domain"
branch_labels = None
depends_on = None


def _supports_alter_constraints() -> bool:
    return op.get_bind().dialect.name != "sqlite"


def upgrade() -> None:
    op.create_table(
        "assessment_task_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("criterion_id", sa.String(length=36), sa.ForeignKey("methodology_criteria.id"), nullable=False),
        sa.Column("indicator_id", sa.String(length=36), sa.ForeignKey("methodology_indicators.id"), nullable=False),
        sa.Column("prompt_template_id", sa.String(length=36), sa.ForeignKey("prompt_templates.id"), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("llm_call_id", sa.String(length=36), sa.ForeignKey("llm_calls.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assessment_task_runs_assessment", "assessment_task_runs", ["assessment_id"])
    op.create_index("ix_assessment_task_runs_status", "assessment_task_runs", ["status"])

    op.add_column("llm_calls", sa.Column("analysis_id", sa.String(length=36), nullable=True))
    op.add_column("llm_calls", sa.Column("assessment_id", sa.String(length=36), nullable=True))
    op.add_column("llm_calls", sa.Column("task_run_id", sa.String(length=36), nullable=True))
    op.add_column("llm_calls", sa.Column("criterion_id", sa.String(length=36), nullable=True))
    op.add_column("llm_calls", sa.Column("indicator_id", sa.String(length=36), nullable=True))
    op.add_column("llm_calls", sa.Column("prompt_template_id", sa.String(length=36), nullable=True))
    if _supports_alter_constraints():
        op.create_foreign_key("fk_llm_calls_analysis_id", "llm_calls", "analyses", ["analysis_id"], ["id"])
        op.create_foreign_key("fk_llm_calls_assessment_id", "llm_calls", "assessments", ["assessment_id"], ["id"])
        op.create_foreign_key("fk_llm_calls_task_run_id", "llm_calls", "assessment_task_runs", ["task_run_id"], ["id"])
        op.create_foreign_key("fk_llm_calls_criterion_id", "llm_calls", "methodology_criteria", ["criterion_id"], ["id"])
        op.create_foreign_key("fk_llm_calls_indicator_id", "llm_calls", "methodology_indicators", ["indicator_id"], ["id"])
        op.create_foreign_key(
            "fk_llm_calls_prompt_template_id",
            "llm_calls",
            "prompt_templates",
            ["prompt_template_id"],
            ["id"],
        )

    op.add_column("assessment_indicator_results", sa.Column("assessment_id", sa.String(length=36), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("evidence_json", sa.JSON(), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("recommendations_json", sa.JSON(), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("prompt_template_id", sa.String(length=36), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("prompt_version", sa.String(length=128), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("llm_call_id", sa.String(length=36), nullable=True))
    op.add_column("assessment_indicator_results", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.add_column(
        "assessment_indicator_results",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    if _supports_alter_constraints():
        op.create_foreign_key(
            "fk_indicator_results_assessment_id",
            "assessment_indicator_results",
            "assessments",
            ["assessment_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_indicator_results_prompt_template_id",
            "assessment_indicator_results",
            "prompt_templates",
            ["prompt_template_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_indicator_results_llm_call_id",
            "assessment_indicator_results",
            "llm_calls",
            ["llm_call_id"],
            ["id"],
        )


def downgrade() -> None:
    if _supports_alter_constraints():
        op.drop_constraint("fk_indicator_results_llm_call_id", "assessment_indicator_results", type_="foreignkey")
        op.drop_constraint("fk_indicator_results_prompt_template_id", "assessment_indicator_results", type_="foreignkey")
        op.drop_constraint("fk_indicator_results_assessment_id", "assessment_indicator_results", type_="foreignkey")
    op.drop_column("assessment_indicator_results", "created_at")
    op.drop_column("assessment_indicator_results", "idempotency_key")
    op.drop_column("assessment_indicator_results", "llm_call_id")
    op.drop_column("assessment_indicator_results", "prompt_version")
    op.drop_column("assessment_indicator_results", "prompt_template_id")
    op.drop_column("assessment_indicator_results", "confidence")
    op.drop_column("assessment_indicator_results", "recommendations_json")
    op.drop_column("assessment_indicator_results", "evidence_json")
    op.drop_column("assessment_indicator_results", "summary")
    op.drop_column("assessment_indicator_results", "assessment_id")

    if _supports_alter_constraints():
        op.drop_constraint("fk_llm_calls_prompt_template_id", "llm_calls", type_="foreignkey")
        op.drop_constraint("fk_llm_calls_indicator_id", "llm_calls", type_="foreignkey")
        op.drop_constraint("fk_llm_calls_criterion_id", "llm_calls", type_="foreignkey")
        op.drop_constraint("fk_llm_calls_task_run_id", "llm_calls", type_="foreignkey")
        op.drop_constraint("fk_llm_calls_assessment_id", "llm_calls", type_="foreignkey")
        op.drop_constraint("fk_llm_calls_analysis_id", "llm_calls", type_="foreignkey")
    op.drop_column("llm_calls", "prompt_template_id")
    op.drop_column("llm_calls", "indicator_id")
    op.drop_column("llm_calls", "criterion_id")
    op.drop_column("llm_calls", "task_run_id")
    op.drop_column("llm_calls", "assessment_id")
    op.drop_column("llm_calls", "analysis_id")

    op.drop_index("ix_assessment_task_runs_status", table_name="assessment_task_runs")
    op.drop_index("ix_assessment_task_runs_assessment", table_name="assessment_task_runs")
    op.drop_table("assessment_task_runs")

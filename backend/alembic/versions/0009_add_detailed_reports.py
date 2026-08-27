"""add detailed reports

Revision ID: 0009_add_detailed_reports
Revises: 0008_add_analysis_mode
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_detailed_reports"
down_revision = "0008_add_analysis_mode"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("detailed_reports"):
        return
    op.create_table(
        "detailed_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("report_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id"),
        sa.UniqueConstraint("report_id"),
    )
    op.create_index("ix_detailed_reports_analysis", "detailed_reports", ["analysis_id"])
    op.create_index("ix_detailed_reports_status", "detailed_reports", ["status"])


def downgrade() -> None:
    if _has_table("detailed_reports"):
        op.drop_index("ix_detailed_reports_status", table_name="detailed_reports")
        op.drop_index("ix_detailed_reports_analysis", table_name="detailed_reports")
        op.drop_table("detailed_reports")

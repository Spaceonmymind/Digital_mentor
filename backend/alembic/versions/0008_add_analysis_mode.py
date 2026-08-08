"""add analysis mode

Revision ID: 0008_add_analysis_mode
Revises: 0007_startup_vkr_p112_report
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_analysis_mode"
down_revision = "0007_startup_vkr_p112_report"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("analyses", "mode"):
        op.add_column("analyses", sa.Column("mode", sa.String(length=32), nullable=False, server_default="standard"))
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("analyses", "mode", server_default=None)


def downgrade() -> None:
    if _has_column("analyses", "mode"):
        op.drop_column("analyses", "mode")

"""add llm calls trace table

Revision ID: 0002_add_llm_calls
Revises: 0001_initial
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_llm_calls"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("requested_model", sa.String(length=255), nullable=False),
        sa.Column("actual_model", sa.String(length=255), nullable=True),
        sa.Column("aggregator", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("finish_reason", sa.String(length=64), nullable=True),
        sa.Column("temperature", sa.Numeric(4, 2), nullable=True),
        sa.Column("max_completion_tokens", sa.Integer(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_rub", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")

"""run summary cache

Persistent tier (not rebuilt by recompute): the AI summary of each run, keyed by the hash of its run context.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.create_table(
        "run_summary_cache",
        sa.Column("workout_id", sa.String(64), primary_key=True),
        sa.Column("context_hash", sa.String(64), primary_key=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("run_summary_cache")

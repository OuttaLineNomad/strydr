"""workout_plan.tap_per: what a live tap means (move, or a whole round)

Persistent tier (user input); not a pipeline input, so no recompute. Existing plans keep tap-per-move.

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    # Plain ADD COLUMN: a batch rebuild would drop the expression index uq_workout_plan_name_lower (not reflectable).
    op.add_column('workout_plan', sa.Column('tap_per', sa.String(length=8), nullable=False, server_default='move'))


def downgrade() -> None:
    op.drop_column('workout_plan', 'tap_per')

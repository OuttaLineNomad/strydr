"""sleep before each run

workout_detail gains sleep: the night before the run and the next morning's resting HR and HRV (analytic tier,
rebuilt every recompute from daily_metric).

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    with op.batch_alter_table('workout_detail') as b:
        b.add_column(sa.Column('sleep', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('workout_detail') as b:
        b.drop_column('sleep')

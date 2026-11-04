"""run/walk split

Analytic tier (rebuilt every recompute): workout_detail gains runwalk, period_summary gains run_s and walk_s.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    with op.batch_alter_table('workout_detail') as b:
        b.add_column(sa.Column('runwalk', sa.JSON(), nullable=True))
    with op.batch_alter_table('period_summary') as b:
        b.add_column(sa.Column('run_s', sa.Float(), nullable=False, server_default='0'))
        b.add_column(sa.Column('walk_s', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('period_summary') as b:
        b.drop_column('walk_s')
        b.drop_column('run_s')
    with op.batch_alter_table('workout_detail') as b:
        b.drop_column('runwalk')

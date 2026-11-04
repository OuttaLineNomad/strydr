"""workout_session.set_rungs: the easier ladder rung actually done for a set

Persistent tier (user input). Nullable JSON {"move_index:instance": rung}; not a pipeline input.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    with op.batch_alter_table('workout_session') as b:
        b.add_column(sa.Column('set_rungs', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('workout_session') as b:
        b.drop_column('set_rungs')

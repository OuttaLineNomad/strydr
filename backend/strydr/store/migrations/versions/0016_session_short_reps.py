"""workout_session.short_reps: the reps done in each EMOM minute flagged as fell short

Persistent tier (user input). Nullable JSON {"minute": reps|null}; not a pipeline input.

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    with op.batch_alter_table('workout_session') as b:
        b.add_column(sa.Column('short_reps', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('workout_session') as b:
        b.drop_column('short_reps')

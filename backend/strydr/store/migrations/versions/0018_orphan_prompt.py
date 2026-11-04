"""workout_session.source and the orphan_dismissal table

Persistent tier (user input); not a pipeline input, so no recompute.

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    with op.batch_alter_table('workout_session') as b:
        b.add_column(sa.Column('source', sa.String(length=8), nullable=True))
    op.create_table(
        'orphan_dismissal',
        sa.Column('workout_id', sa.String(length=64), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table('orphan_dismissal')
    with op.batch_alter_table('workout_session') as b:
        b.drop_column('source')

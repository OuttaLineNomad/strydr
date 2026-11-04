"""workout_session: the saved record of each live home workout

Persistent tier (user input), no foreign keys. Sessions are not a pipeline input: a recompute never reads or writes them.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.create_table('workout_session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=True),
    sa.Column('plan', sa.JSON(), nullable=False),
    sa.Column('weight_kg', sa.Float(), nullable=True),
    sa.Column('start_utc', sa.DateTime(), nullable=False),
    sa.Column('end_utc', sa.DateTime(), nullable=False),
    sa.Column('events', sa.JSON(), nullable=False),
    sa.Column('rounds_done', sa.Integer(), nullable=False),
    sa.Column('partial_moves', sa.Integer(), nullable=False),
    sa.Column('fell_short', sa.JSON(), nullable=False),
    sa.Column('active_s', sa.Integer(), nullable=False),
    sa.Column('overtime_s', sa.Integer(), nullable=False),
    sa.Column('matched_workout_id', sa.String(length=64), nullable=True),
    sa.Column('effort', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workout_session_plan_id'), 'workout_session', ['plan_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workout_session_plan_id'), table_name='workout_session')
    op.drop_table('workout_session')

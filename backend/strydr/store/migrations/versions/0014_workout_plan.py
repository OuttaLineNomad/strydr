"""workout_plan: saved home-workout plans

Persistent tier (user input), no foreign keys. Plans are not a pipeline input: a recompute never reads or writes them.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.create_table('workout_plan',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('format', sa.String(length=8), nullable=False),
    sa.Column('cap_min', sa.Integer(), nullable=True),
    sa.Column('emom_min', sa.Integer(), nullable=True),
    sa.Column('rounds', sa.Integer(), nullable=True),
    sa.Column('moves', sa.JSON(), nullable=False),
    sa.Column('video_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_workout_plan_name_lower', 'workout_plan', [sa.text('lower(name)')], unique=True)


def downgrade() -> None:
    op.drop_index('uq_workout_plan_name_lower', table_name='workout_plan')
    op.drop_table('workout_plan')

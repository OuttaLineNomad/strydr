"""workout_type_override: the runner's corrections to workout types

Persistent tier (user input). A recompute never touches it; normalize applies it on every write.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.create_table('workout_type_override',
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('type', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('workout_id')
    )


def downgrade() -> None:
    op.drop_table('workout_type_override')

"""workout_carry: extra weight carried on a workout

Persistent tier (user input), no foreign key. Display only: a recompute never reads or writes it.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.create_table('workout_carry',
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('weight_kg', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('workout_id')
    )


def downgrade() -> None:
    op.drop_table('workout_carry')

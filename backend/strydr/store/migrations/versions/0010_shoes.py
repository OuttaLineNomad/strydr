"""shoes: shoe list, default-shoe history and per-run shoe choices

Persistent tier (user input), no foreign keys. Shoes are not a pipeline input: a recompute never reads or writes them.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.create_table('shoe',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('retired', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_shoe_name_lower', 'shoe', [sa.text('lower(name)')], unique=True)
    op.create_table('shoe_default',
    sa.Column('from_date', sa.String(length=10), nullable=False),
    sa.Column('shoe_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('from_date')
    )
    op.create_table('workout_shoe',
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('shoe_id', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('workout_id')
    )


def downgrade() -> None:
    op.drop_table('workout_shoe')
    op.drop_table('shoe_default')
    op.drop_index('uq_shoe_name_lower', table_name='shoe')
    op.drop_table('shoe')

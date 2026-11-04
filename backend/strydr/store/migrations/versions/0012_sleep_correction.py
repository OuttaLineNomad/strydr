"""sleep_correction: the runner's own hours for a night recorded short

Persistent tier (user input), no foreign key. A pipeline input: derive overlays it on the night's total sleep.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.create_table('sleep_correction',
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('hours', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('local_date')
    )


def downgrade() -> None:
    op.drop_table('sleep_correction')

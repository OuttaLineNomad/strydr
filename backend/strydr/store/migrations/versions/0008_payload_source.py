"""payload source

Which exporter a raw payload came from (hae|apple). Workouts from different sources are the same activity when
they start together; two from one source never are.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.add_column("raw_payload", sa.Column("source", sa.String(8), nullable=False, server_default="hae"))


def downgrade() -> None:
    with op.batch_alter_table("raw_payload") as b:
        b.drop_column("source")

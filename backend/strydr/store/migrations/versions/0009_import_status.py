"""import status

Which adapter version normalized each raw payload (so reparse and the staleness check work per source), and the
persistent progress record of an Apple Health export import.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

HAE_ADAPTER_VERSION = 2  # frozen: HAE's version when this migration was written
revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.add_column("raw_payload", sa.Column("adapter_version", sa.Integer(), nullable=True))
    # Existing payloads are all HAE (0008's default): the oldest version among the rows they produced, or the current one.
    op.execute(sa.text(f"""
        UPDATE raw_payload SET adapter_version = COALESCE(
            (SELECT MIN(v) FROM (
                SELECT adapter_version AS v FROM workout WHERE workout.payload_id = raw_payload.id
                UNION ALL
                SELECT adapter_version AS v FROM daily_metric WHERE daily_metric.payload_id = raw_payload.id)),
            {HAE_ADAPTER_VERSION})
        WHERE status = 'processed'"""))
    op.create_table(
        "import_status",
        sa.Column("payload_id", sa.Integer(), sa.ForeignKey("raw_payload.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("workouts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("merged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kept_existing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nights", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_from", sa.String(10), nullable=True),
        sa.Column("date_to", sa.String(10), nullable=True),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("import_status")
    with op.batch_alter_table("raw_payload") as b:
        b.drop_column("adapter_version")

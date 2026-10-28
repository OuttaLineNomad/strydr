"""initial: raw, canonical, job, auth and settings tables

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "raw_payload",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sha256", sa.String(64), unique=True),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("error", sa.String(200)),
    )
    op.create_table(
        "raw_chunk",
        sa.Column("payload_id", sa.Integer, sa.ForeignKey("raw_payload.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seq", sa.Integer, primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload_id", sa.Integer, sa.ForeignKey("raw_payload.id", ondelete="SET NULL")),
        sa.Column("as_of", sa.String(10)),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("run_after", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_error", sa.String(200)),
    )
    op.create_index("ix_job_status_run_after", "job", ["status", "run_after"])
    op.create_table(
        "workout",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workout_id", sa.String(64), nullable=False, unique=True),
        sa.Column("type", sa.String(8), nullable=False),
        sa.Column("is_indoor", sa.Boolean, nullable=False),
        sa.Column("start_utc", sa.DateTime, nullable=False),
        sa.Column("end_utc", sa.DateTime, nullable=False),
        sa.Column("utc_offset_s", sa.Integer, nullable=False),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("duration_s", sa.Float),
        sa.Column("distance_m", sa.Float),
        sa.Column("avg_speed_mps", sa.Float),
        sa.Column("max_speed_mps", sa.Float),
        sa.Column("avg_hr", sa.Float),
        sa.Column("max_hr", sa.Float),
        sa.Column("avg_cadence", sa.Float),
        sa.Column("elevation_gain_m", sa.Float),
        sa.Column("energy_kcal", sa.Float),
        sa.Column("temperature_c", sa.Float),
        sa.Column("humidity_pct", sa.Float),
        sa.Column("effort_score", sa.Float),
        sa.Column("effort_estimated", sa.Boolean),
        sa.Column("quality_flags", sa.JSON, nullable=False),
        sa.Column("series_count", sa.Integer, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("adapter_version", sa.Integer, nullable=False),
        sa.Column("payload_id", sa.Integer, sa.ForeignKey("raw_payload.id", ondelete="SET NULL")),
        sa.Column("received_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_workout_start_utc", "workout", ["start_utc"])
    op.create_index("ix_workout_local_date", "workout", ["local_date"])
    op.create_table(
        "sample_series",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workout_id", sa.String(64), sa.ForeignKey("workout.workout_id", ondelete="CASCADE"), nullable=False),
        sa.Column("series", sa.String(32), nullable=False),
        sa.Column("n_samples", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("adapter_version", sa.Integer, nullable=False),
        sa.UniqueConstraint("workout_id", "series"),
    )
    op.create_table(
        "daily_metric",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("units", sa.String(32), nullable=False),
        sa.Column("value", sa.Float),
        sa.Column("extra", sa.JSON),
        sa.Column("series_count", sa.Integer, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("adapter_version", sa.Integer, nullable=False),
        sa.Column("payload_id", sa.Integer, sa.ForeignKey("raw_payload.id", ondelete="SET NULL")),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("metric", "local_date"),
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("ingest_token_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )

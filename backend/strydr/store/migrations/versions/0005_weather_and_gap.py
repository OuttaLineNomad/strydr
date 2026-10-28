"""weather and grade adjusted pace

workout_detail gains conditions and gap (analytic tier, rebuilt every recompute). workout_weather and
weather_cache hold the opt-in fetched weather (canonical tier, written only by the fetch_weather job).

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    with op.batch_alter_table('workout_detail') as b:
        b.add_column(sa.Column('conditions', sa.JSON(), nullable=True))
        b.add_column(sa.Column('gap', sa.JSON(), nullable=True))
    op.create_table('workout_weather',
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('temp_c', sa.Float(), nullable=True),
    sa.Column('apparent_c', sa.Float(), nullable=True),
    sa.Column('dew_point_c', sa.Float(), nullable=True),
    sa.Column('humidity_pct', sa.Float(), nullable=True),
    sa.Column('wind_ms', sa.Float(), nullable=True),
    sa.Column('wind_dir_deg', sa.Float(), nullable=True),
    sa.Column('gust_ms', sa.Float(), nullable=True),
    sa.Column('precip_mm_h', sa.Float(), nullable=True),
    sa.Column('cloud_pct', sa.Float(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['workout_id'], ['workout.workout_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workout_id')
    )
    op.create_table('weather_cache',
    sa.Column('cell', sa.String(length=16), nullable=False),
    sa.Column('utc_date', sa.String(length=10), nullable=False),
    sa.Column('hourly', sa.JSON(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('cell', 'utc_date')
    )


def downgrade() -> None:
    op.drop_table('weather_cache')
    op.drop_table('workout_weather')
    with op.batch_alter_table('workout_detail') as b:
        b.drop_column('gap')
        b.drop_column('conditions')

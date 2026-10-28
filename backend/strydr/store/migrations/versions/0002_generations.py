"""analytic generations, privacy zones and user-authored tables

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table('generation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('as_of', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('insight_feedback',
    sa.Column('insight_key', sa.String(length=160), nullable=False),
    sa.Column('thumb', sa.String(length=8), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('insight_key')
    )
    op.create_table('privacy_zone',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lon', sa.Float(), nullable=False),
    sa.Column('radius_m', sa.Float(), nullable=False),
    sa.Column('offset_north_m', sa.Float(), nullable=False),
    sa.Column('offset_east_m', sa.Float(), nullable=False),
    sa.Column('trim_m', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('route_override',
    sa.Column('workout_a', sa.String(length=64), nullable=False),
    sa.Column('workout_b', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=8), nullable=False),
    sa.PrimaryKeyConstraint('workout_a', 'workout_b')
    )
    op.create_table('week_note',
    sa.Column('week_id', sa.String(length=8), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('week_id')
    )
    op.create_table('workout_note',
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('rpe', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('workout_id')
    )
    op.create_table('best_effort',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('distance_key', sa.String(length=16), nullable=False),
    sa.Column('time_s', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id', 'distance_key')
    )
    op.create_table('current_generation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('id = 1'),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('daily_load',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('load', sa.Float(), nullable=False),
    sa.Column('fitness', sa.Float(), nullable=True),
    sa.Column('fatigue', sa.Float(), nullable=True),
    sa.Column('form', sa.Float(), nullable=True),
    sa.Column('estimated', sa.Boolean(), nullable=False),
    sa.Column('by_type', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'local_date')
    )
    op.create_table('data_quality_issue',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=True),
    sa.Column('stage', sa.String(length=32), nullable=False),
    sa.Column('error', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_quality_issue_generation_id'), 'data_quality_issue', ['generation_id'], unique=False)
    op.create_table('day_class',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('is_hard', sa.Boolean(), nullable=False),
    sa.Column('is_rest', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'local_date')
    )
    op.create_table('insight_fact',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('insight_key', sa.String(length=160), nullable=False),
    sa.Column('rule_id', sa.String(length=64), nullable=False),
    sa.Column('subject', sa.String(length=96), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('number', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(length=16), nullable=True),
    sa.Column('evidence', sa.JSON(), nullable=False),
    sa.Column('template_id', sa.String(length=64), nullable=False),
    sa.Column('text_template', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'insight_key')
    )
    op.create_table('period_summary',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('period_id', sa.String(length=10), nullable=False),
    sa.Column('start_date', sa.String(length=10), nullable=False),
    sa.Column('distance_m', sa.Float(), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=False),
    sa.Column('run_count', sa.Integer(), nullable=False),
    sa.Column('long_run_count', sa.Integer(), nullable=False),
    sa.Column('elevation_gain_m', sa.Float(), nullable=True),
    sa.Column('zone_seconds', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'kind', 'period_id')
    )
    op.create_table('profile_result',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('hrmax', sa.Integer(), nullable=True),
    sa.Column('hrmax_source', sa.String(length=16), nullable=False),
    sa.Column('zone_bounds_bpm', sa.JSON(), nullable=True),
    sa.Column('easy_ceiling_bpm', sa.Float(), nullable=True),
    sa.Column('rhr_7d_median', sa.Float(), nullable=True),
    sa.Column('rhr_30d_baseline', sa.Float(), nullable=True),
    sa.Column('hrv_60d_baseline', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id')
    )
    op.create_table('record',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(length=8), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=True),
    sa.Column('local_date', sa.String(length=10), nullable=True),
    sa.Column('period_id', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'key')
    )
    op.create_table('route',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('route_key', sa.String(length=64), nullable=False),
    sa.Column('run_count', sa.Integer(), nullable=False),
    sa.Column('display_geometry', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'route_key')
    )
    op.create_table('route_section',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.String(length=80), nullable=False),
    sa.Column('route_key', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=1), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('start_m', sa.Float(), nullable=False),
    sa.Column('end_m', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'section_id')
    )
    op.create_table('workout_detail',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('splits_km', sa.JSON(), nullable=True),
    sa.Column('splits_mi', sa.JSON(), nullable=True),
    sa.Column('hr_series', sa.JSON(), nullable=True),
    sa.Column('pace_series', sa.JSON(), nullable=True),
    sa.Column('elevation_series', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id')
    )
    op.create_table('workout_display',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('display_geometry', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id')
    )
    op.create_table('workout_load',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('trimp', sa.Float(), nullable=True),
    sa.Column('estimated', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id')
    )
    op.create_table('workout_route',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('route_key', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id')
    )
    op.create_table('workout_summary',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('is_long_run', sa.Boolean(), nullable=False),
    sa.Column('zone_seconds', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'workout_id')
    )

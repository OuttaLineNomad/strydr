"""real shapes for the load, day, route and insight tables; phrasing cache

Analytic tables whose shape changed are dropped and recreated (AD-14); the migration enqueues a recompute.
`phrasing_cache` is persistent tier and is never touched by a recompute.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"

CHANGED = ("workout_load", "daily_load", "day_class", "route", "workout_route", "route_section", "insight_fact")


def upgrade() -> None:
    for table in CHANGED:
        op.drop_table(table)
    op.create_table('phrasing_cache',
    sa.Column('insight_key', sa.String(length=160), nullable=False),
    sa.Column('fact_hash', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('insight_key', 'fact_hash')
    )
    op.create_table('daily_load',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('load', sa.Float(), nullable=False),
    sa.Column('by_type', sa.JSON(), nullable=False),
    sa.Column('estimated', sa.Boolean(), nullable=False),
    sa.Column('n_workouts', sa.Integer(), nullable=False),
    sa.Column('fitness', sa.Float(), nullable=False),
    sa.Column('fatigue', sa.Float(), nullable=False),
    sa.Column('form', sa.Float(), nullable=True),
    sa.Column('form_pct', sa.Float(), nullable=True),
    sa.Column('warmup', sa.Boolean(), nullable=False),
    sa.Column('acwr', sa.Float(), nullable=True),
    sa.Column('ramp_pct', sa.Float(), nullable=True),
    sa.Column('raw_state', sa.String(length=16), nullable=True),
    sa.Column('training_state', sa.String(length=16), nullable=True),
    sa.Column('state_since', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'local_date')
    )
    op.create_table('day_class',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('has_run', sa.Boolean(), nullable=False),
    sa.Column('is_hard', sa.Boolean(), nullable=False),
    sa.Column('is_rest', sa.Boolean(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('load', sa.Float(), nullable=False),
    sa.Column('hard_seconds', sa.Float(), nullable=False),
    sa.Column('reasons', sa.JSON(), nullable=False),
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
    sa.Column('phrase_hash', sa.String(length=64), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('week_id', sa.String(length=8), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'insight_key')
    )
    op.create_index(op.f('ix_insight_fact_local_date'), 'insight_fact', ['local_date'], unique=False)
    op.create_index(op.f('ix_insight_fact_rule_id'), 'insight_fact', ['rule_id'], unique=False)
    op.create_index(op.f('ix_insight_fact_subject'), 'insight_fact', ['subject'], unique=False)
    op.create_index(op.f('ix_insight_fact_week_id'), 'insight_fact', ['week_id'], unique=False)
    op.create_table('route',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('route_key', sa.String(length=64), nullable=False),
    sa.Column('run_count', sa.Integer(), nullable=False),
    sa.Column('reference_id', sa.String(length=64), nullable=False),
    sa.Column('sibling_key', sa.String(length=64), nullable=True),
    sa.Column('distance_m', sa.Float(), nullable=False),
    sa.Column('first_date', sa.String(length=10), nullable=False),
    sa.Column('last_date', sa.String(length=10), nullable=False),
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
    sa.Column('gain_m', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'section_id')
    )
    op.create_index(op.f('ix_route_section_route_key'), 'route_section', ['route_key'], unique=False)
    op.create_table('section_result',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.String(length=80), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('route_key', sa.String(length=64), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('time_s', sa.Float(), nullable=True),
    sa.Column('avg_hr', sa.Float(), nullable=True),
    sa.Column('comparable', sa.Boolean(), nullable=False),
    sa.Column('n', sa.Integer(), nullable=False),
    sa.Column('baseline_time_s', sa.Float(), nullable=True),
    sa.Column('baseline_hr', sa.Float(), nullable=True),
    sa.Column('gap_s', sa.Float(), nullable=True),
    sa.Column('spread_s', sa.Float(), nullable=True),
    sa.Column('z', sa.Float(), nullable=True),
    sa.Column('direction', sa.String(length=8), nullable=True),
    sa.Column('fires', sa.Boolean(), nullable=False),
    sa.Column('reasons', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['generation_id'], ['generation.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('generation_id', 'section_id', 'workout_id')
    )
    op.create_index(op.f('ix_section_result_route_key'), 'section_result', ['route_key'], unique=False)
    op.create_table('workout_load',
    sa.Column('generation_id', sa.Integer(), nullable=False),
    sa.Column('workout_id', sa.String(length=64), nullable=False),
    sa.Column('type', sa.String(length=8), nullable=False),
    sa.Column('local_date', sa.String(length=10), nullable=False),
    sa.Column('trimp', sa.Float(), nullable=False),
    sa.Column('estimated', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('coverage', sa.Float(), nullable=True),
    sa.Column('rpe', sa.Integer(), nullable=True),
    sa.Column('hr_max', sa.Float(), nullable=True),
    sa.Column('hr_rest', sa.Float(), nullable=True),
    sa.Column('b', sa.Float(), nullable=True),
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
    op.create_index(op.f('ix_workout_route_route_key'), 'workout_route', ['route_key'], unique=False)
    op.add_column('profile_result', sa.Column('rhr_baseline_mean', sa.Float(), nullable=True))
    op.add_column('profile_result', sa.Column('rhr_baseline_sd', sa.Float(), nullable=True))
    op.add_column('profile_result', sa.Column('rhr_baseline_days', sa.Integer(), nullable=True))
    op.add_column('profile_result', sa.Column('hrv_baseline_mean', sa.Float(), nullable=True))
    op.add_column('profile_result', sa.Column('hrv_baseline_sd', sa.Float(), nullable=True))
    op.add_column('profile_result', sa.Column('hrv_baseline_days', sa.Integer(), nullable=True))
    op.add_column('workout_summary', sa.Column('hr_time_s', sa.Float(), nullable=True))
    op.add_column('workout_summary', sa.Column('easy_time_s', sa.Float(), nullable=True))
    op.add_column('workout_summary', sa.Column('hr_coverage', sa.Float(), nullable=True))
    op.add_column('workout_summary', sa.Column('minutes', sa.JSON(), nullable=True))

    # Only when there is something to rebuild. No as_of: the worker uses today in home_tz.
    op.execute(sa.text("INSERT INTO job (type, status, attempts, run_after, created_at) "
                       "SELECT 'recompute', 'pending', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                       "WHERE EXISTS (SELECT 1 FROM generation)"))


def downgrade() -> None:
    raise NotImplementedError("forward-only (AD-14)")

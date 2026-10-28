"""Insight rules (tier 1, plus the tier-2 conditions rules). Importing this package registers every rule (see `registry.registered_rules`)."""
from . import (  # noqa: F401
    attaboys_streaks,
    cardiac_drift,
    conditions,
    hard_days,
    hrv,
    intensity,
    long_run_spike,
    no_rest_day,
    pace_at_fixed_hr,
    resting_hr,
    sleep,
    training_state,
    weekly_ramp,
)

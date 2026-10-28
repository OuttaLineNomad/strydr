"""Synthetic builders for the load/days/insight tests. No real data; everything is invented."""
from datetime import date, timedelta

from strydr.pipeline.derive.days import DayClass
from strydr.pipeline.derive.load import LoadParams
from strydr.pipeline.insights.models import (
    Baseline,
    DailyValue,
    DerivedSnapshot,
    MinutePoint,
    PeriodVolume,
    RunSummary,
)
from strydr.pipeline.insights.thresholds import load_thresholds

AS_OF = date(2026, 10, 26)  # a Monday (ISO week 2026-W44)


def th(overrides=None):
    return load_thresholds(overrides)


def load_params() -> LoadParams:
    return LoadParams.from_mapping(th().section("load"))


def minutes(n=60, hr=140.0, speed=3.0, alt=0.0, hr2=None, speed2=None, alt_slope=0.0, split=None):
    """n per-minute points. hr2/speed2 apply from minute `split` on (default n//2); alt rises alt_slope m/min."""
    out = []
    for i in range(n):
        second = i >= (n // 2 if split is None else split)
        out.append(
            MinutePoint(
                hr=hr2 if (second and hr2 is not None) else hr,
                speed_mps=speed2 if (second and speed2 is not None) else speed,
                altitude_m=alt + alt_slope * i,
            )
        )
    return tuple(out)


def run(wid, d, dist_km=10.0, dur_min=60.0, **kw) -> RunSummary:
    base = dict(
        workout_id=wid,
        local_date=d,
        distance_m=dist_km * 1000,
        duration_s=dur_min * 60,
        avg_speed_mps=dist_km * 1000 / (dur_min * 60),
        avg_hr=140.0,
        elevation_gain_m=0.0,
        temperature_c=None,
        is_indoor=False,
        is_long_run=False,
        is_easy_intended=False,
        hr_time_s=dur_min * 60 - 600,
        easy_time_s=dur_min * 60 - 600,
        hr_coverage=1.0,
        minutes=None,
    )
    base.update(kw)
    return RunSummary(**base)


def weekly(*specs) -> tuple[PeriodVolume, ...]:
    """specs: (monday, distance_km, run_count)."""
    out = []
    for monday, km, n in specs:
        wid = monday.strftime("%G-W%V")
        out.append(PeriodVolume(wid, monday, monday + timedelta(days=6), km * 1000, km * 360, n))
    return tuple(out)


def day_classes(start, end, hard=(), rest=(), load=50.0, loads=None):
    """One DayClass per date. `rest` and `hard` are sets of dates; default is an active, non-hard day."""
    out = []
    d = start
    while d <= end:
        ld = (loads or {}).get(d, 0.0 if d in rest else load)
        out.append(DayClass(d, d not in rest, d in hard, d in rest, "rest" if d in rest else "run", ld, 0.0))
        d += timedelta(days=1)
    return tuple(out)


def snapshot(**kw) -> DerivedSnapshot:
    base = dict(as_of=AS_OF, units="km", hr_max=190.0, easy_ceiling_bpm=152.0, history_start=AS_OF - timedelta(days=200))
    base.update(kw)
    return DerivedSnapshot(**base)


def daily(start, values) -> tuple[DailyValue, ...]:
    return tuple(DailyValue(start + timedelta(days=i), v) for i, v in enumerate(values))


def baseline(mean, sd, n=30) -> Baseline:
    return Baseline(mean, sd, n)

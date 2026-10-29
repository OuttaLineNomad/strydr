"""Shoe resolution, shared by the run detail page and the shoe totals. A run's shoe is derived at read time from the
user's tables (workout_shoe overrides, shoe_default history), so a reparse or recompute never reassigns anything."""
from bisect import bisect_right
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.store import models


def resolve(s: Session, workouts: Iterable) -> dict[str, tuple[int | None, str]]:
    """{workout_id: (shoe_id | None, source)} with source 'chosen' (an override row, even a null one) or 'default'
    (a run covered by the default history). Workouts with no shoe and no source are (None, 'default')."""
    workouts = list(workouts)
    if not workouts:
        return {}
    chosen = dict(s.execute(select(models.WorkoutShoe.workout_id, models.WorkoutShoe.shoe_id)).all())
    history = sorted(s.execute(select(models.ShoeDefault.from_date, models.ShoeDefault.shoe_id)).all())
    dates = [d for d, _ in history]
    out: dict[str, tuple[int | None, str]] = {}
    for w in workouts:
        if w.workout_id in chosen:
            out[w.workout_id] = (chosen[w.workout_id], "chosen")
        elif w.type == "run" and (i := bisect_right(dates, w.local_date)) > 0:
            out[w.workout_id] = (history[i - 1][1], "default")
        else:
            out[w.workout_id] = (None, "default")
    return out


def totals(s: Session) -> dict[int, tuple[float, int]]:
    """{shoe_id: (distance_m, runs)} over every workout resolved to a shoe (a null distance counts as 0)."""
    rows = s.execute(select(models.Workout.workout_id, models.Workout.type, models.Workout.local_date,
                            models.Workout.distance_m)).all()
    dist = {r.workout_id: r.distance_m or 0.0 for r in rows}
    acc: dict[int, tuple[float, int]] = {}
    for wid, (shoe_id, _) in resolve(s, rows).items():
        if shoe_id is not None:
            d, n = acc.get(shoe_id, (0.0, 0))
            acc[shoe_id] = (d + dist[wid], n + 1)
    return acc


def current_default(s: Session, today: str) -> models.ShoeDefault | None:
    return s.execute(select(models.ShoeDefault).where(models.ShoeDefault.from_date <= today)
                     .order_by(models.ShoeDefault.from_date.desc()).limit(1)).scalar_one_or_none()

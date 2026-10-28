"""One-off type corrections: `strydr relabel --from walk --to run --through YYYY-MM-DD`.

Writes a WorkoutTypeOverride per matching workout, so the correction survives a
reparse or a re-sent payload, then enqueues a recompute. Workouts after the
cutoff, and every future import, keep the type the source sends.
"""
from datetime import datetime, timezone

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from strydr.jobs import queue
from strydr.store import models, settings

TYPES = ("run", "walk", "hike")


def relabel(engine: Engine, src: str, dst: str, through: str, default_tz: str = "UTC") -> int:
    if src not in TYPES or dst not in TYPES or src == dst:
        raise ValueError("types must be two different values of run, walk, hike")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as s:
        ids = list(s.execute(select(models.Workout.workout_id)
                             .where(models.Workout.type == src, models.Workout.local_date <= through)).scalars())
        for wid in ids:
            s.merge(models.WorkoutTypeOverride(workout_id=wid, type=dst, created_at=now))
        if ids:
            s.execute(update(models.Workout).where(models.Workout.workout_id.in_(ids)).values(type=dst))
            queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))
        s.commit()
    return len(ids)

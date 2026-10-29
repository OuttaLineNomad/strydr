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


def set_type(s: Session, workout_id: str, dst: str, default_tz: str = "UTC", enqueue: bool = True) -> None:
    """Pin one workout's type (override row, Workout.type, recompute job); the caller commits."""
    if dst not in TYPES:
        raise ValueError("type must be one of run, walk, hike")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    s.merge(models.WorkoutTypeOverride(workout_id=workout_id, type=dst, created_at=now))
    s.execute(update(models.Workout).where(models.Workout.workout_id == workout_id).values(type=dst))
    if enqueue:
        queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))


def relabel(engine: Engine, src: str, dst: str, through: str, default_tz: str = "UTC") -> int:
    if src not in TYPES or dst not in TYPES or src == dst:
        raise ValueError("types must be two different values of run, walk, hike")
    with Session(engine) as s:
        ids = list(s.execute(select(models.Workout.workout_id)
                             .where(models.Workout.type == src, models.Workout.local_date <= through)).scalars())
        for wid in ids:
            set_type(s, wid, dst, default_tz, enqueue=False)
        if ids:
            queue.enqueue_recompute(s, queue.local_today(settings.read(s, default_tz).home_tz))
        s.commit()
    return len(ids)

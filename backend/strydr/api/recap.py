"""Recap of one calendar month or year, assembled at read time from existing tables. Runs only (FR-7a)."""
import calendar as cal
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from strydr import shoes as shoe_resolver
from strydr.api import schemas as sc
from strydr.api.common import Api, workout_out
from strydr.api.weeks import _summaries
from strydr.jobs import queue
from strydr.store import generations, models, settings
from strydr.store.generations import in_current, scoped

PERIOD_RE = re.compile(r"^\d{4}(-\d{2})?$")
TOP = 3


def _bounds(period: str) -> tuple[date, date]:
    try:
        if len(period) == 4:
            y = int(period)
            return date(y, 1, 1), date(y, 12, 31)
        first = date(int(period[:4]), int(period[5:]), 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="not a month or year") from None
    return first, first.replace(day=cal.monthrange(first.year, first.month)[1])


def _previous(period: str) -> str:
    if len(period) == 4:
        return f"{int(period) - 1:04d}"
    prev = (date(int(period[:4]), int(period[5:]), 1) - timedelta(days=1))
    return f"{prev:%Y-%m}"


def _totals(s: Session, period: str) -> sc.RecapTotals:
    lo, hi = _bounds(period)
    rows = s.execute(scoped(models.PeriodSummary, models.PeriodSummary.kind == "month",
                            models.PeriodSummary.period_id.like(f"{period}%"))).scalars().all()
    elev = [p.elevation_gain_m for p in rows if p.elevation_gain_m is not None]
    active = s.execute(select(func.count(func.distinct(models.Workout.local_date))).where(
        models.Workout.type == "run", models.Workout.local_date >= lo.isoformat(),
        models.Workout.local_date <= hi.isoformat())).scalar_one()
    return sc.RecapTotals(
        period=period, distance_m=sum(p.distance_m for p in rows), duration_s=sum(p.duration_s for p in rows),
        run_count=sum(p.run_count for p in rows), long_run_count=sum(p.long_run_count for p in rows),
        elevation_gain_m=sum(elev) if elev else None, active_days=active)


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/recap", tags=["recap"], dependencies=api.auth)

    @r.get("/{period}", response_model=sc.RecapOut)
    def get_recap(period: str) -> sc.RecapOut:
        if not PERIOD_RE.match(period) or int(period[:4]) < 1000:
            raise HTTPException(status_code=422, detail="period must look like 2026 or 2026-10")
        first, last = _bounds(period)
        lo, hi = first.isoformat(), last.isoformat()
        with generations.read_snapshot(api.engine) as s:
            gen = s.execute(select(models.Generation).join(
                models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
            as_of = gen.as_of if gen else None
            today = date.fromisoformat(queue.local_today(settings.read(s, api.default_tz).home_tz))
            if first > today:
                raise HTTPException(status_code=422, detail="period is in the future")

            totals = _totals(s, period)
            try:
                previous = _totals(s, _previous(period))
            except HTTPException:  # year 1 has no year before it
                previous = sc.RecapTotals(period=_previous(period), distance_m=0.0, duration_s=0.0, run_count=0,
                                          long_run_count=0, elevation_gain_m=None, active_days=0)
            runs = s.execute(select(models.Workout).where(
                models.Workout.type == "run", models.Workout.local_date >= lo, models.Workout.local_date <= hi)
                .order_by(models.Workout.start_utc)).scalars().all()
            ids = [w.workout_id for w in runs]

            longest = sorted(runs, key=lambda w: w.distance_m or 0.0, reverse=True)[:TOP]
            names: dict[str, set[str]] = {}
            long_runs: dict[str, bool] = {}
            top_routes: list[sc.RecapRoute] = []
            if ids:
                top_ids = [w.workout_id for w in longest]
                for wid, name in s.execute(select(models.SampleSeries.workout_id, models.SampleSeries.series)
                                           .where(models.SampleSeries.workout_id.in_(top_ids))):
                    names.setdefault(wid, set()).add(name)
                carry = dict(s.execute(select(models.WorkoutCarry.workout_id, models.WorkoutCarry.weight_kg).where(
                    models.WorkoutCarry.workout_id.in_(top_ids))).all())
                long_runs = dict(s.execute(select(models.WorkoutSummary.workout_id, models.WorkoutSummary.is_long_run).where(
                    in_current(models.WorkoutSummary), models.WorkoutSummary.workout_id.in_(top_ids))).all())
                counts: dict[str, int] = {}
                for key in s.execute(select(models.WorkoutRoute.route_key).where(
                        in_current(models.WorkoutRoute), models.WorkoutRoute.workout_id.in_(ids))).scalars():
                    counts[key] = counts.get(key, 0) + 1
                dist = dict(s.execute(select(models.Route.route_key, models.Route.distance_m).where(
                    in_current(models.Route), models.Route.route_key.in_(list(counts)))).all())
                top_routes = [sc.RecapRoute(route_key=k, distance_m=dist[k], runs=n)
                              for k, n in sorted(((k, n) for k, n in counts.items() if k in dist), key=lambda kn: (-kn[1], kn[0]))[:TOP]]

            per_shoe: dict[int, list] = {}
            dist_of = {w.workout_id: w.distance_m or 0.0 for w in runs}
            for wid, (shoe_id, _) in shoe_resolver.resolve(s, runs).items():
                if shoe_id is not None:
                    acc = per_shoe.setdefault(shoe_id, [0.0, 0])
                    acc[0] += dist_of[wid]
                    acc[1] += 1
            shoe_rows = {x.id: x for x in s.execute(select(models.Shoe)).scalars()} if per_shoe else {}
            shoes = sorted((sc.RecapShoe(id=i, name=shoe_rows[i].name, retired=shoe_rows[i].retired, distance_m=d, runs=n)
                            for i, (d, n) in per_shoe.items() if n > 0 and i in shoe_rows), key=lambda x: -x.distance_m)

            days = s.execute(scoped(models.DailyLoad, models.DailyLoad.local_date >= lo, models.DailyLoad.local_date <= hi)
                             .order_by(models.DailyLoad.local_date)).scalars().all()
            fitness = None
            if days:
                picked = days if len(period) == 7 else [
                    d for d in days if date.fromisoformat(d.local_date).weekday() == 6 or d is days[-1]]
                fitness = sc.RecapFitness(start=days[0].fitness, end=days[-1].fitness, series=[
                    sc.RecapFitnessPoint(local_date=d.local_date, fitness=d.fitness) for d in picked])

            weeks = s.execute(scoped(models.PeriodSummary, models.PeriodSummary.kind == "week",
                                     models.PeriodSummary.start_date >= lo, models.PeriodSummary.start_date <= hi,
                                     models.PeriodSummary.distance_m > 0)
                              .order_by(models.PeriodSummary.distance_m.desc(), models.PeriodSummary.start_date)
                              .limit(TOP)).scalars().all()
            best = []
            if weeks:
                rank = {p.start_date: i for i, p in enumerate(weeks)}
                by_date = _summaries(s, sorted(date.fromisoformat(p.start_date) for p in weeks))
                best = sorted(by_date, key=lambda w: rank[w.week_start])

            return sc.RecapOut(
                period=period, kind="year" if len(period) == 4 else "month", start_date=lo, end_date=hi, as_of=as_of,
                is_current=first <= today <= last, totals=totals, previous=previous,
                longest_runs=[workout_out(w, names.get(w.workout_id, set()), long_runs.get(w.workout_id), carry.get(w.workout_id)) for w in longest],
                top_routes=top_routes, shoes=shoes, fitness=fitness, best_weeks=best)

    return r

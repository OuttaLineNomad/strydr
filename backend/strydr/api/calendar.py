"""Training calendar: one month as whole weeks, every day's workouts and load, and the month against the last."""
import calendar as cal
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.store import generations, models
from strydr.store.generations import scoped

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _month_start(month: str) -> date:
    try:
        return date(int(month[:4]), int(month[5:]), 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="not a month") from None


def _prev(first: date) -> date:
    return (first - timedelta(days=1)).replace(day=1)


def _totals(p: models.PeriodSummary | None, month: str) -> sc.MonthTotals:
    return sc.MonthTotals(month=month, distance_m=p.distance_m if p else 0.0, duration_s=p.duration_s if p else 0.0,
                          run_count=p.run_count if p else 0, elevation_gain_m=p.elevation_gain_m if p else None)


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=api.auth)

    @r.get("", response_model=sc.CalendarOut)
    def month_view(month: str | None = Query(None, pattern=MONTH_RE.pattern, description="YYYY-MM, default the month of as_of")) -> sc.CalendarOut:
        with generations.read_snapshot(api.engine) as s:
            gen = s.execute(select(models.Generation).join(
                models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
            as_of = gen.as_of if gen else None
            first = _month_start(month) if month else (date.fromisoformat(as_of) if as_of else date.today()).replace(day=1)
            last = first.replace(day=cal.monthrange(first.year, first.month)[1])
            lo, hi = first - timedelta(days=first.weekday()), last + timedelta(days=6 - last.weekday())
            loads = {d.local_date: d.load for d in s.execute(scoped(
                models.DailyLoad, models.DailyLoad.local_date >= lo.isoformat(), models.DailyLoad.local_date <= hi.isoformat())).scalars()}
            classes = {d.local_date: d for d in s.execute(scoped(
                models.DayClass, models.DayClass.local_date >= lo.isoformat(), models.DayClass.local_date <= hi.isoformat())).scalars()}
            ws = s.execute(select(models.Workout).where(
                models.Workout.local_date >= lo.isoformat(), models.Workout.local_date <= hi.isoformat())
                .order_by(models.Workout.start_utc)).scalars().all()
            prev = _prev(first)
            ids = [f"{first:%Y-%m}", f"{prev:%Y-%m}"]
            periods = {p.period_id: _totals(p, p.period_id) for p in s.execute(scoped(
                models.PeriodSummary, models.PeriodSummary.kind == "month", models.PeriodSummary.period_id.in_(ids))).scalars()}
            by_day: dict[str, list[sc.CalendarWorkout]] = {}
            for w in ws:
                by_day.setdefault(w.local_date, []).append(sc.CalendarWorkout(
                    workout_id=w.workout_id, type=w.type, distance_m=w.distance_m, duration_s=w.duration_s))
            classes = {k: (c.kind, c.is_hard) for k, c in classes.items()}

        days = []
        for i in range((hi - lo).days + 1):
            d = (lo + timedelta(days=i)).isoformat()
            kind, hard = classes.get(d, (None, None))
            days.append(sc.CalendarDay(local_date=d, in_month=first.isoformat() <= d <= last.isoformat(),
                                       kind=kind, is_hard=hard,
                                       load=loads.get(d, 0.0), workouts=by_day.get(d, [])))
        mine = [d for d in days if d.in_month]
        runs = [w.distance_m for d in mine for w in d.workouts if w.type == "run" and w.distance_m]
        return sc.CalendarOut(
            month=ids[0], as_of=as_of, days=days, totals=periods.get(ids[0]) or _totals(None, ids[0]),
            previous=periods.get(ids[1]) or _totals(None, ids[1]), longest_run_m=max(runs) if runs else None,
            active_days=sum(1 for d in mine if d.workouts), rest_days=sum(1 for d in mine if d.kind == "rest"))

    return r

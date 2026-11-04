"""Week list and week view, with the week note (FR-14..FR-16)."""
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339, workout_out
from strydr.api.insights import feed_query, insight_out
from strydr.store import generations, models
from strydr.store.generations import in_current, scoped
from strydr.store.util import utcnow

WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
EASY_ZONES = 3  # zones 1-3 are at or below the easy ceiling (80% of HRmax by default)


def monday_of(week_id: str) -> date:
    if not WEEK_RE.match(week_id):
        raise HTTPException(status_code=422, detail="week_id must look like 2026-W44")
    try:
        return date.fromisocalendar(int(week_id[:4]), int(week_id[6:]), 1)
    except ValueError:
        raise HTTPException(status_code=422, detail="not an ISO week") from None


def _wid(d: date) -> str:
    return d.strftime("%G-W%V")


def _walk_pct(p: models.PeriodSummary | None) -> float | None:
    total = (p.run_s + p.walk_s) if p else 0.0
    return round(p.walk_s / total * 100, 1) if total > 0 else None


def _summaries(s: Session, mondays: list[date]) -> list[sc.WeekSummaryOut]:
    first, last = mondays[0], mondays[-1] + timedelta(days=6)
    ids = [_wid(m) for m in mondays]
    periods = {p.period_id: p for p in s.execute(scoped(
        models.PeriodSummary, models.PeriodSummary.kind == "week", models.PeriodSummary.period_id.in_(ids))).scalars()}
    days = s.execute(scoped(models.DailyLoad, models.DailyLoad.local_date >= first.isoformat(),
                            models.DailyLoad.local_date <= last.isoformat()).order_by(models.DailyLoad.local_date)).scalars().all()
    counts = dict(s.execute(select(models.InsightFact.week_id, func.count()).where(
        in_current(models.InsightFact), models.InsightFact.week_id.in_(ids)).group_by(models.InsightFact.week_id)).all())
    noted = set(s.execute(select(models.WeekNote.week_id).where(models.WeekNote.week_id.in_(ids))).scalars())
    out = []
    for m in mondays:
        wid = _wid(m)
        mine = [d for d in days if m.isoformat() <= d.local_date <= (m + timedelta(days=6)).isoformat()]
        by_type: dict[str, float] = {}
        for d in mine:
            for t, v in d.by_type.items():
                by_type[t] = by_type.get(t, 0.0) + v
        p = periods.get(wid)
        zones = p.zone_seconds if p else None
        total = sum(zones) if zones else 0
        end = mine[-1] if mine else None
        out.append(sc.WeekSummaryOut(
            week_id=wid, week_start=m.isoformat(), week_end=(m + timedelta(days=6)).isoformat(),
            distance_m=p.distance_m if p else 0.0, duration_s=p.duration_s if p else 0.0,
            run_count=p.run_count if p else 0, long_run_count=p.long_run_count if p else 0,
            elevation_gain_m=p.elevation_gain_m if p else None,
            intensity=sc.IntensityMix(zone_seconds=zones, easy_share_pct=sum(zones[:EASY_ZONES]) / total * 100 if total else None),
            walk_pct=_walk_pct(p),
            load=sc.WeekLoad(total=sum(d.load for d in mine), by_type=by_type, estimated=any(d.estimated for d in mine),
                             fitness=end.fitness if end else None, fatigue=end.fatigue if end else None,
                             form_pct=end.form_pct if end else None),
            insight_count=counts.get(wid, 0), has_note=wid in noted))
    return out


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/weeks", tags=["weeks"], dependencies=api.auth)

    @r.get("", response_model=list[sc.WeekSummaryOut])
    def list_weeks(
        from_week: str | None = Query(None, alias="from", pattern=WEEK_RE.pattern, description="first week_id, default 11 weeks before `to`"),
        to_week: str | None = Query(None, alias="to", pattern=WEEK_RE.pattern, description="last week_id, default the week of as_of"),
    ) -> list[sc.WeekSummaryOut]:
        with generations.read_snapshot(api.engine) as s:
            gen = s.execute(select(models.Generation).join(
                models.CurrentGeneration, models.CurrentGeneration.generation_id == models.Generation.id)).scalar_one_or_none()
            if gen is None:
                return []
            end = monday_of(to_week) if to_week else date.fromisoformat(gen.as_of) - timedelta(days=date.fromisoformat(gen.as_of).weekday())
            start = monday_of(from_week) if from_week else end - timedelta(weeks=11)
            if start > end or (end - start).days > 520 * 7:
                raise HTTPException(status_code=422, detail="invalid week range")
            mondays = [start + timedelta(weeks=i) for i in range((end - start).days // 7 + 1)]
            return list(reversed(_summaries(s, mondays)))  # newest first

    @r.get("/{week_id}", response_model=sc.WeekDetailOut)
    def get_week(week_id: str) -> sc.WeekDetailOut:
        monday = monday_of(week_id)
        lo, hi = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
        with generations.read_snapshot(api.engine) as s:
            summary = _summaries(s, [monday])[0]
            loads = {d.local_date: d for d in s.execute(scoped(
                models.DailyLoad, models.DailyLoad.local_date >= lo, models.DailyLoad.local_date <= hi)).scalars()}
            classes = {d.local_date: d for d in s.execute(scoped(
                models.DayClass, models.DayClass.local_date >= lo, models.DayClass.local_date <= hi)).scalars()}
            days = []
            for i in range(7):
                d = (monday + timedelta(days=i)).isoformat()
                load, cls = loads.get(d), classes.get(d)
                days.append(sc.DayLoadOut(
                    local_date=d, load=load.load if load else 0.0, by_type=dict(load.by_type) if load else {},
                    estimated=load.estimated if load else False, is_hard=cls.is_hard if cls else None,
                    is_rest=cls.is_rest if cls else None))
            ws = s.execute(select(models.Workout).where(
                models.Workout.type == "run", models.Workout.local_date >= lo, models.Workout.local_date <= hi)
                .order_by(models.Workout.start_utc)).scalars().all()
            ids = [w.workout_id for w in ws]
            names: dict[str, set[str]] = {}
            long_runs: dict[str, bool] = {}
            if ids:
                for wid, name in s.execute(select(models.SampleSeries.workout_id, models.SampleSeries.series)
                                           .where(models.SampleSeries.workout_id.in_(ids))):
                    names.setdefault(wid, set()).add(name)
                long_runs = dict(s.execute(select(models.WorkoutSummary.workout_id, models.WorkoutSummary.is_long_run).where(
                    in_current(models.WorkoutSummary), models.WorkoutSummary.workout_id.in_(ids))).all())
            insights = [insight_out(*row) for row in s.execute(feed_query(models.InsightFact.week_id == week_id)).all()]
            note = s.get(models.WeekNote, week_id)
            return sc.WeekDetailOut(
                **summary.model_dump(), days=days,
                runs=[workout_out(w, names.get(w.workout_id, set()), long_runs.get(w.workout_id)) for w in ws],
                insights=insights,
                note=sc.WeekNoteOut(text=note.text, updated_at=rfc3339(note.updated_at)) if note else None)

    @r.put("/{week_id}/note", response_model=sc.WeekNoteOut)
    def put_week_note(week_id: str, body: sc.WeekNoteIn) -> sc.WeekNoteOut:
        monday_of(week_id)
        with Session(api.engine) as s:  # a week note is not a pipeline input (AD-1): no recompute
            note = s.get(models.WeekNote, week_id) or models.WeekNote(week_id=week_id)
            note.text, note.updated_at = body.text, utcnow()
            s.add(note)
            s.commit()
            return sc.WeekNoteOut(text=note.text, updated_at=rfc3339(note.updated_at))

    @r.delete("/{week_id}/note", status_code=204)
    def delete_week_note(week_id: str) -> Response:
        monday_of(week_id)
        with Session(api.engine) as s:
            note = s.get(models.WeekNote, week_id)
            if note is not None:
                s.delete(note)
                s.commit()
        return Response(status_code=204)

    return r

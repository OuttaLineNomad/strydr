"""Insights stage (AD-8): pure rules over a `DerivedSnapshot`, run by `engine.run_rules`, worded by `templates.render`."""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.context import Context
from strydr.pipeline.derive.routes.matching import load_thresholds as load_route_thresholds
from strydr.pipeline.insights import engine, same_route, snapshot
from strydr.pipeline.insights.keys import is_valid_key
from strydr.pipeline.insights.models import InsightFact
from strydr.pipeline.insights.templates import fact_hash, render
from strydr.pipeline.profile import Profile
from strydr.store import generations, models

log = logging.getLogger("strydr.insights")


def run(ctx: Context, profile: Profile) -> None:
    gid, th = ctx.generation_id, ctx.th
    units = "mi" if profile.units == "imperial" else "km"
    snap = snapshot.build(ctx, profile)
    facts = engine.run_rules(snap, th)

    rt = load_route_thresholds()
    lookback = ctx.as_of - timedelta(days=th.section("engine")["run_lookback_days"] - 1)
    with Session(ctx.engine) as s:
        results = s.execute(select(models.SectionResult).where(models.SectionResult.generation_id == gid)).scalars().all()
        sections = {r.section_id: (r.kind, r.idx) for r in s.execute(
            select(models.RouteSection).where(models.RouteSection.generation_id == gid)).scalars()}
        carried = {wid: kg for wid, kg in s.execute(select(models.WorkoutCarry.workout_id, models.WorkoutCarry.weight_kg)) if kg > 0}
    seen = {f.insight_key for f in facts}
    for f in same_route.build(results, sections, units, lookback, rt.window_days, rt.hr_match_bpm, carried):
        if is_valid_key(f.insight_key) and f.insight_key not in seen:
            facts.append(f)
            seen.add(f.insight_key)

    rows = []
    for f in facts:
        try:
            local, week = _when(f, ctx.as_of)
            rows.append(models.InsightFact(
                generation_id=gid, insight_key=f.insight_key, rule_id=f.rule_id, subject=f.subject, period=f.period,
                kind=f.kind, number=f.number, unit=f.unit, evidence=f.evidence, template_id=f.template_id,
                text_template=render(f, units), phrase_hash=fact_hash(f, units), local_date=local, week_id=week))
        except Exception as e:  # one bad fact never fails the generation (AD-5)
            log.warning("insight skipped: %s", type(e).__name__)
            generations.add_rows(ctx.engine, [models.DataQualityIssue(
                generation_id=gid, workout_id=None, stage="insights", error=type(e).__name__)])
    generations.add_rows(ctx.engine, rows)


def _when(f: InsightFact, as_of: date) -> tuple[str, str]:
    """(local date used to order the feed, ISO week the insight belongs to)."""
    if len(f.period) == 10:
        d = date.fromisoformat(f.period)
        return f.period, d.strftime("%G-W%V")
    monday = date.fromisocalendar(int(f.period[:4]), int(f.period[6:]), 1)
    return min(monday + timedelta(days=6), as_of).isoformat(), f.period

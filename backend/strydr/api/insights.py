"""Insight feed, reasoning and feedback (FR-10, FR-12, FR-15, FR-19, FR-20)."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api, rfc3339
from strydr.pipeline.phrasing import summary
from strydr.store import generations, models
from strydr.store.generations import in_current
from strydr.store.util import utcnow

DISCLAIMER = "Not medical advice."
SUMMARY_PREFIX = "run-summary/"


def insight_out(row: models.InsightFact, ai_text: str | None, thumb: str | None) -> sc.InsightOut:
    return sc.InsightOut(
        insight_key=row.insight_key, rule_id=row.rule_id, subject=row.subject, period=row.period, kind=row.kind,
        number=row.number, unit=row.unit, text=ai_text or row.text_template, text_source="ai" if ai_text else "template",
        local_date=row.local_date, week_id=row.week_id,
        run_id=row.subject.removeprefix("run/") if row.subject.startswith("run/") else None, thumb=thumb)


def feed_query(*where):
    """Insights of the current generation with their fresh AI phrasing (matching hash) and the runner's thumb."""
    return (
        select(models.InsightFact, models.PhrasingCache.text, models.InsightFeedback.thumb)
        .outerjoin(models.PhrasingCache, (models.PhrasingCache.insight_key == models.InsightFact.insight_key)
                   & (models.PhrasingCache.fact_hash == models.InsightFact.phrase_hash))
        .outerjoin(models.InsightFeedback, models.InsightFeedback.insight_key == models.InsightFact.insight_key)
        .where(in_current(models.InsightFact), *where)
        .order_by(models.InsightFact.local_date.desc(), models.InsightFact.insight_key))


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/insights", tags=["insights"], dependencies=api.auth)

    @r.get("", response_model=sc.InsightFeedOut)
    def list_insights(
        subject: str | None = Query(None, description="exact subject: run/{id}, week/{id}, route/{key} or athlete"),
        run: str | None = Query(None, description="a workout_id: that run's insights"),
        week: str | None = Query(None, pattern=r"^\d{4}-W\d{2}$", description="a week_id: insights dated in that ISO week"),
        rule_id: str | None = None, kind: str | None = None,
        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    ) -> sc.InsightFeedOut:
        where = []
        if subject:
            where.append(models.InsightFact.subject == subject)
        if run:
            where.append(models.InsightFact.subject == f"run/{run}")
        if week:
            where.append(models.InsightFact.week_id == week)
        if rule_id:
            where.append(models.InsightFact.rule_id == rule_id)
        if kind:
            where.append(models.InsightFact.kind == kind)
        with generations.read_snapshot(api.engine) as s:
            total = s.execute(select(func.count()).select_from(models.InsightFact).where(
                in_current(models.InsightFact), *where)).scalar_one()
            rows = s.execute(feed_query(*where).limit(limit).offset(offset)).all()
            return sc.InsightFeedOut(items=[insight_out(*row) for row in rows], total=total, limit=limit,
                                     offset=offset, disclaimer=DISCLAIMER)

    def one(s: Session, key: str):
        row = s.execute(feed_query(models.InsightFact.insight_key == key)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="insight not found")
        return row

    # `:path` because the key contains slashes (AD-6): rule:run/{workout_id}:{date}
    @r.get("/{insight_key:path}", response_model=sc.InsightDetailOut)
    def get_insight(insight_key: str) -> sc.InsightDetailOut:
        with generations.read_snapshot(api.engine) as s:
            fact, ai_text, thumb = one(s, insight_key)
            ev = fact.evidence or {}
            return sc.InsightDetailOut(
                **insight_out(fact, ai_text, thumb).model_dump(), template_id=fact.template_id,
                text_template=fact.text_template,
                reasoning=sc.InsightReasoning(rule=ev.get("rule", fact.rule_id), data=ev.get("data", {}), note=ev.get("note", "")))

    @r.put("/{insight_key:path}/feedback", response_model=sc.FeedbackOut)
    def put_feedback(insight_key: str, body: sc.FeedbackIn) -> sc.FeedbackOut:
        served = None
        if insight_key.startswith(SUMMARY_PREFIX):  # a run summary has no InsightFact
            with generations.read_snapshot(api.engine) as rs:
                served = summary.serve(rs, insight_key.removeprefix(SUMMARY_PREFIX), api.default_tz)
        with Session(api.engine) as s:
            if insight_key.startswith(SUMMARY_PREFIX):
                if served is None:
                    raise HTTPException(status_code=404, detail="summary not found")
                snapshot = {"context_hash": served[2], "text": served[0], "source": served[1]}
            else:
                fact = s.execute(select(models.InsightFact).where(
                    in_current(models.InsightFact), models.InsightFact.insight_key == insight_key)).scalar_one_or_none()
                if fact is None:
                    raise HTTPException(status_code=404, detail="insight not found")
                # No FK into the analytic tier (AD-6): the fact at rating time is kept so tuning survives recomputes.
                snapshot = {"number": fact.number, "unit": fact.unit, "evidence": fact.evidence}
            row = s.get(models.InsightFeedback, insight_key) or models.InsightFeedback(insight_key=insight_key)
            row.thumb, row.snapshot, row.updated_at = body.thumb, snapshot, utcnow()
            s.add(row)
            s.commit()
            return sc.FeedbackOut(insight_key=insight_key, thumb=row.thumb, snapshot=sc.FeedbackSnapshot(**snapshot),
                                  updated_at=rfc3339(row.updated_at))

    @r.delete("/{insight_key:path}/feedback", status_code=204)
    def delete_feedback(insight_key: str) -> None:
        with Session(api.engine) as s:
            row = s.get(models.InsightFeedback, insight_key)
            if row is not None:
                s.delete(row)
                s.commit()

    return r

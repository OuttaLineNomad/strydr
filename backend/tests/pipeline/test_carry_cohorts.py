"""Story 13: carried and uncarried runs are two cohorts; carry shapes hard days, drift, same-route and the wording."""
from datetime import date, datetime, timedelta

import pytest
from insight_synth import AS_OF, day_classes, minutes, run, snapshot, th
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.pipeline.derive.days import DayParams, DayWorkout, classify_days
from strydr.pipeline.insights import same_route
from strydr.pipeline.insights.engine import run_rules
from strydr.pipeline.insights.rules._common import runs_between
from strydr.pipeline.insights.rules.cardiac_drift import cardiac_drift
from strydr.pipeline.insights.rules.carry import carry as carry_rule
from strydr.pipeline.insights.rules.conditions import pace_by_conditions
from strydr.pipeline.insights.rules.hard_days import hard_day_stacking
from strydr.pipeline.insights.rules.intensity import easy_creep
from strydr.pipeline.insights.rules.pace_at_fixed_hr import pace_at_fixed_hr
from strydr.pipeline.insights.templates import BANNED_TERMS, render
from strydr.pipeline.insights.templates._format import carry_text
from strydr.store import models

from helpers import add_run, recompute_now

D = timedelta(days=1)
P = DayParams.from_mapping(th().section("days"))
KG = 11.3


def _ids(facts):
    return {f.insight_key: f for f in facts}


# ---- wording ----

@pytest.mark.parametrize("kg,units,text", [(11.3, "mi", "25 lb"), (11.3, "km", "11.3 kg"), (10.0, "km", "10 kg"),
                                           (0.1, "mi", "1 lb"), (0.01, "km", "0.1 kg")])
def test_carry_text_rounds_like_the_carry_field(kg, units, text):
    assert carry_text(kg, units) == text


# ---- carry fact ----

def test_each_carried_run_gets_a_carry_fact_and_uncarried_runs_none():
    snap = snapshot(runs=(run("a", AS_OF - D, carry_kg=KG), run("b", AS_OF - 2 * D)))
    (f,) = carry_rule(snap, th(), [])
    assert f.insight_key == f"carry:run/a:{(AS_OF - D).isoformat()}" and f.template_id == "carry-run"
    assert render(f, "mi") == "You ran this one carrying 25 lb." and render(f, "km") == "You ran this one carrying 11.3 kg."
    assert not any(t in render(f, "mi").lower() for t in BANNED_TERMS)


# ---- trend rules per cohort ----

def _band_runs(recent_speed, old_speed, carried=False, prefix="n"):
    mk = lambda wid, ago, speed: run(  # noqa: E731
        wid, AS_OF - ago * D, 8.0, 40, minutes=minutes(40, hr=140.0, speed=speed), carry_kg=KG if carried else None)
    return (tuple(mk(f"{prefix}{i}", 2 + 5 * i, recent_speed) for i in range(4))
            + tuple(mk(f"{prefix}o{i}", 30 + 5 * i, old_speed) for i in range(4)))


def test_uncarried_pace_at_hr_ignores_carried_runs():
    carried_slow = _band_runs(2.0, 2.0, carried=True, prefix="c")
    assert pace_at_fixed_hr(snapshot(runs=_band_runs(3.15, 3.0)), th(), []) == pace_at_fixed_hr(
        snapshot(runs=_band_runs(3.15, 3.0) + carried_slow), th(), [])


def test_carried_pace_at_hr_has_its_own_key_and_template():
    snap = snapshot(runs=_band_runs(3.15, 3.0) + _band_runs(2.3, 2.5, carried=True, prefix="c"))
    facts = _ids(pace_at_fixed_hr(snap, th(), []))
    assert set(facts) == {"pace-at-fixed-hr:week/2026-W44:2026-W44", "pace-at-fixed-hr:athlete:2026-W44"}
    f = facts["pace-at-fixed-hr:athlete:2026-W44"]
    assert f.template_id == "pace-at-hr-slower-carry" and f.number == 8.0
    assert render(f, "km").startswith("At about 140 bpm, your carried runs are 8% slower")
    assert facts["pace-at-fixed-hr:week/2026-W44:2026-W44"].template_id == "pace-at-hr-faster"


def test_carried_cohort_below_threshold_is_silent():
    runs = _band_runs(3.15, 3.0) + _band_runs(2.3, 2.5, carried=True, prefix="c")[:6]
    assert [f.template_id for f in pace_at_fixed_hr(snapshot(runs=runs), th(), [])] == ["pace-at-hr-faster"]


def _easy(i, hr, carried=False):
    return run(f"{'c' if carried else 'e'}{i}", AS_OF - (1 + 2 * i) * D, is_easy_intended=True, avg_hr=hr,
               carry_kg=KG if carried else None)


def test_easy_creep_runs_per_cohort():
    unc = tuple(_easy(i, 140.0) for i in range(5))
    car = tuple(_easy(i, 160.0, True) for i in range(5))
    facts = easy_creep(snapshot(runs=unc + car), th(), [])
    assert facts[0].template_id == "easy-creep-ceiling-carry"
    assert [f.insight_key for f in facts] == ["easy-creep:athlete:2026-W44"]
    assert easy_creep(snapshot(runs=unc), th(), []) == []
    assert easy_creep(snapshot(runs=tuple(_easy(i, 160.0) for i in range(5)) + car), th(), [])[0].template_id == "easy-creep-ceiling"


def _cond(dew, band="warm"):
    return {"dew_point_c": dew, "band": band}


def test_pace_by_conditions_per_cohort_with_distinct_keys():
    def mk(carried):
        out = []
        for i in range(6):
            out.append(run(f"{carried}w{i}", AS_OF - 2 * i * D, 3.2, 33.0, is_easy_intended=True, conditions=_cond(19.0),
                           carry_kg=KG if carried else None))
            out.append(run(f"{carried}c{i}", AS_OF - (2 * i + 1) * D, 3.2, 30.0, is_easy_intended=True, conditions=_cond(6.0, "ideal"),
                           carry_kg=KG if carried else None))
        return tuple(out)

    facts = _ids(pace_by_conditions(snapshot(runs=mk(False) + mk(True)), th(), []))
    assert set(facts) == {"pace-by-conditions:athlete:2026-W44", "pace-by-conditions:week/2026-W44:2026-W44"}
    assert facts["pace-by-conditions:week/2026-W44:2026-W44"].template_id == "pace-by-conditions-carry"
    assert "easy carried runs" in render(facts["pace-by-conditions:week/2026-W44:2026-W44"], "km")
    only_carried = pace_by_conditions(snapshot(runs=mk(True)), th(), [])
    assert [f.template_id for f in only_carried] == ["pace-by-conditions-carry"]


def test_carry_rule_can_be_switched_off():
    snap = snapshot(runs=(run("a", AS_OF - D, carry_kg=KG),))
    assert len(carry_rule(snap, th(), [])) == 1
    assert carry_rule(snap, th({"carry": {"enabled": False}}), []) == []


def test_uncarried_drift_evidence_has_no_carry_key():
    (g,) = cardiac_drift(snapshot(runs=(_drift_run(),)), th(), [])
    assert "carried_kg" not in g.evidence["data"]


def test_runs_between_cohort_filter():
    snap = snapshot(runs=(run("a", AS_OF - D, carry_kg=KG), run("b", AS_OF - D)))
    assert [r.workout_id for r in runs_between(snap, AS_OF - 2 * D, AS_OF, True)] == ["a"]
    assert [r.workout_id for r in runs_between(snap, AS_OF - 2 * D, AS_OF, False)] == ["b"]
    assert len(runs_between(snap, AS_OF - 2 * D, AS_OF)) == 2


# ---- drift ----

def _drift_run(carry=None, temp=None, hr2=160.0):
    return run("d1", AS_OF - D, 10.0, 60, temperature_c=temp, minutes=minutes(60, hr=140.0, hr2=hr2, split=35), carry_kg=carry)


def test_carried_drift_uses_the_carry_template_and_stays_out_of_the_trend():
    (f,) = cardiac_drift(snapshot(runs=(_drift_run(KG),)), th(), [])
    assert f.template_id == "cardiac-drift-high-carry" and f.evidence["data"]["in_trend"] is False
    assert f.evidence["data"]["carried_kg"] == KG
    assert "carrying 25 lb" in render(f, "mi")
    (g,) = cardiac_drift(snapshot(runs=(_drift_run(),)), th(), [])
    assert g.template_id == "cardiac-drift-high" and g.evidence["data"]["in_trend"] is True


def test_carry_wins_over_heat_and_solid_drift_is_labelled():
    (f,) = cardiac_drift(snapshot(runs=(_drift_run(KG, temp=30.0),)), th(), [])
    assert f.template_id == "cardiac-drift-high-carry"
    (s,) = cardiac_drift(snapshot(runs=(_drift_run(KG, hr2=140.0),)), th(), [])
    assert s.template_id == "cardiac-drift-solid-carry" and "Carrying 11.3 kg" in render(s, "km")


# ---- hard days ----

def test_carried_walk_or_hike_adds_no_hard_time_but_a_carried_run_and_uncarried_walk_do():
    def hard(w):
        return classify_days({D0: [w]}, D0, D0, P)[0].is_hard

    D0 = date(2026, 10, 1)
    assert hard(DayWorkout("walk", 3600, 60, hard_s=1500))
    assert not hard(DayWorkout("walk", 3600, 60, hard_s=1500, carried=True))
    assert not hard(DayWorkout("hike", 3600, 60, hard_s=1500, carried=True))
    assert hard(DayWorkout("run", 3600, 60, hard_s=1500, carried=True))
    mixed = classify_days({D0: [DayWorkout("walk", 1800, 30, hard_s=600, carried=True), DayWorkout("run", 1800, 30, hard_s=600)]}, D0, D0, P)[0]
    assert not mixed.is_hard and mixed.hard_seconds == 600


def test_stacking_names_carried_run_days():
    start = AS_OF - 40 * D
    days = day_classes(start, AS_OF, hard={AS_OF - D, AS_OF})
    plain = snapshot(days=days, history_start=start)
    (f,) = [x for x in hard_day_stacking(plain, th(), []) if x.subject == "athlete"]
    assert f.template_id == "hard-day-stacking-consecutive" and "carried_days" not in f.evidence["data"]
    carried = snapshot(days=days, history_start=start, carried_run_dates=frozenset({AS_OF}))
    (g,) = [x for x in hard_day_stacking(carried, th(), []) if x.subject == "athlete"]
    assert g.template_id == "hard-day-stacking-consecutive-carry" and g.evidence["data"]["carried_days"] == [AS_OF.isoformat()]
    assert render(g, "km").endswith("and one of them a carried run.")
    window = snapshot(days=day_classes(start, AS_OF, hard={AS_OF - 6 * D, AS_OF - 3 * D, AS_OF}), history_start=start,
                      carried_run_dates=frozenset({AS_OF, AS_OF - 3 * D}))
    (w,) = [x for x in hard_day_stacking(window, th(), []) if x.subject == "athlete"]
    assert w.template_id == "hard-day-stacking-window-carry" and "2 of them carried runs" in render(w, "km")


# ---- no carry: unchanged ----

def test_no_carry_means_no_carry_facts_and_no_carry_templates():
    runs = _band_runs(3.15, 3.0) + (_drift_run(),)
    facts = run_rules(snapshot(runs=runs), th())
    assert facts and not any(f.template_id.endswith("-carry") or f.rule_id == "carry" for f in facts)


# ---- same route ----

class _R:
    def __init__(self, wid, gap):
        self.workout_id, self.section_id, self.local_date = wid, "s1", AS_OF.isoformat()
        self.fires, self.z, self.gap_s, self.n, self.baseline_hr = True, 3.0, gap, 4, 150.0
        self.time_s = self.baseline_time_s = 300.0
        self.avg_hr = 150.0


def test_same_route_fact_for_a_carried_run_uses_the_carry_template():
    out = same_route.build([_R("a", 20.0), _R("b", -20.0)], {"s1": ("k", 1)}, "km", AS_OF - 30 * D, 180, 4.0, {"a": KG})
    by = {f.subject: f for f in out}
    assert by["run/a"].template_id == "same-route-hr-slower-carry" and by["run/b"].template_id == "same-route-hr-faster"
    assert render(by["run/a"], "mi").startswith("Carrying 25 lb at about 150 bpm")
    assert same_route.build([_R("a", 20.0)], {"s1": ("k", 1)}, "km", AS_OF - 30 * D, 180, 4.0)[0].template_id == "same-route-hr-slower"


def test_route_sections_compare_each_run_only_with_its_own_cohort(engine):
    for i in range(5):
        add_run(engine, f"p{i}", datetime(2026, 10, 10 + i, 7), 30, 3.0, hr=[150.0] * 30)
    add_run(engine, "r", datetime(2026, 10, 20, 7), 30, 3.0, hr=[150.0] * 30)
    recompute_now(engine, "2026-10-26")

    def n_for(wid):
        with Session(engine) as s:
            return max(r.n for r in s.execute(select(models.SectionResult).where(models.SectionResult.workout_id == wid)).scalars())

    assert n_for("r") == 5
    with Session(engine) as s:
        for wid in ("p0", "p1"):
            s.add(models.WorkoutCarry(workout_id=wid, weight_kg=KG, updated_at=datetime(2026, 10, 21)))
        s.commit()
    recompute_now(engine, "2026-10-26")
    assert n_for("r") == 3  # p2..p4: the two carried runs dropped out of its baseline
    assert n_for("p1") == 1  # a carried run sees only the carried run before it


# ---- recompute-level wiring ----

def _carry_rows(engine, *wids):
    with Session(engine) as s:
        for wid in wids:
            s.add(models.WorkoutCarry(workout_id=wid, weight_kg=KG, updated_at=datetime(2026, 10, 21)))
        s.commit()


def _day(engine, local_date):
    from strydr.store.generations import in_current
    with Session(engine) as s:
        return s.execute(select(models.DayClass).where(in_current(models.DayClass), models.DayClass.local_date == local_date)).scalar_one()


@pytest.mark.parametrize("carried,hard", [(False, True), (True, False)])
def test_carried_walk_is_not_a_hard_day_after_recompute(engine, carried, hard):
    from helpers import set_hrmax
    set_hrmax(engine, 190)
    add_run(engine, "w", datetime(2026, 10, 20, 7), 30, 1.5, hr=[170.0] * 30, type_="walk")  # 30 min above 88% of 190
    if carried:
        _carry_rows(engine, "w")
    recompute_now(engine, "2026-10-26")
    assert _day(engine, "2026-10-20").is_hard is hard


def test_stacking_fact_names_a_carried_run_day_after_recompute(engine):
    from helpers import set_hrmax
    from strydr.store.generations import in_current
    set_hrmax(engine, 190)
    add_run(engine, "a", datetime(2026, 10, 24, 7), 30, 3.0, hr=[170.0] * 30)
    add_run(engine, "b", datetime(2026, 10, 25, 7), 30, 3.0, hr=[170.0] * 30)
    _carry_rows(engine, "b")
    recompute_now(engine, "2026-10-26")
    with Session(engine) as s:
        f = s.execute(select(models.InsightFact).where(
            in_current(models.InsightFact), models.InsightFact.rule_id == "hard-day-stacking")).scalar_one()
    assert f.template_id == "hard-day-stacking-consecutive-carry" and f.evidence["data"]["carried_days"] == ["2026-10-25"]


def test_carried_run_same_route_fact_uses_the_carry_template(engine):
    for wid, day in (("p1", 10), ("p2", 13), ("p3", 16), ("p4", 19)):
        add_run(engine, wid, datetime(2026, 10, day, 7), 30, 3.0, hr=150.0)
    add_run(engine, "r", datetime(2026, 10, 24, 7), 28, 5400 / (28 * 60), hr=150.0)
    _carry_rows(engine, "p1", "p2", "p3", "p4", "r")
    recompute_now(engine, "2026-10-26")
    from strydr.store.generations import in_current
    with Session(engine) as s:
        f = s.execute(select(models.InsightFact).where(
            in_current(models.InsightFact), models.InsightFact.rule_id == "same-route-hr",
            models.InsightFact.subject == "run/r")).scalar_one()
    assert f.template_id == "same-route-hr-faster-carry" and f.evidence["data"]["carried_kg"] == KG

"""Registry, engine ordering, key stability, thresholds and the template lint."""
import dataclasses
import json
import math
import re
from datetime import date, timedelta

import pytest
from insight_synth import AS_OF, baseline, day_classes, daily, minutes, run, snapshot, th

from strydr.pipeline.derive.load.model import TrainingStateDay
from strydr.pipeline.insights.engine import run_rules, topological_order
from strydr.pipeline.insights.keys import is_valid_key, make_evidence, make_fact
from strydr.pipeline.insights.models import KINDS, InsightFact
from strydr.pipeline.insights.registry import Rule, registered_rules, rule
from strydr.pipeline.insights.templates import BANNED_TERMS, TEMPLATES, render
from strydr.pipeline.insights.templates._format import base_fields
from strydr.pipeline.insights.thresholds import load_thresholds

D = timedelta(days=1)

TIER_1 = {
    "long-run-spike", "weekly-ramp", "attaboys-streaks", "intensity-mix", "easy-creep", "cardiac-drift",
    "resting-hr", "hrv", "pace-at-fixed-hr", "hard-day-stacking", "no-rest-day", "training-state",
}
TIER_2 = {"heat-adjusted-pace", "hill-adjusted-pace", "pace-by-conditions", "short-sleep-run", "effort-by-sleep"}


# ---- registry and engine ----

def test_all_tier_one_rules_plus_training_state_are_registered_with_kebab_ids():
    ids = {r.rule_id for r in registered_rules()}
    assert ids == TIER_1 | TIER_2
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)


def test_every_after_reference_resolves_and_order_respects_it():
    order = [r.rule_id for r in topological_order(registered_rules())]
    for r in registered_rules():
        assert all(order.index(dep) < order.index(r.rule_id) for dep in r.after)
    assert order.index("weekly-ramp") < order.index("attaboys-streaks")
    assert order.index("resting-hr") < order.index("hrv")
    assert order == [r.rule_id for r in topological_order(list(reversed(registered_rules())))]  # input order does not matter


def test_topological_order_rejects_cycles_unknown_and_duplicate_rules():
    a = Rule("a", lambda s, t, p: [], ("b",))
    b = Rule("b", lambda s, t, p: [], ("a",))
    with pytest.raises(ValueError, match="cycle"):
        topological_order([a, b])
    with pytest.raises(ValueError, match="unknown"):
        topological_order([Rule("x", lambda s, t, p: [], ("nope",))])
    with pytest.raises(ValueError, match="duplicate"):
        topological_order([a, a])


def test_registering_rejects_bad_ids_and_duplicates():
    with pytest.raises(ValueError):
        rule("Not_Kebab")(lambda s, t, p: [])
    with pytest.raises(ValueError, match="duplicate"):
        rule("long-run-spike")(lambda s, t, p: [])


def test_engine_passes_prior_facts_in_dependency_order():
    seen = {}

    def first(snap, t, prior):
        return [make_fact("first-rule", "athlete", AS_OF, "observation", 1.0, "x", make_evidence("first-rule", {}, "n"), "t")]

    def second(snap, t, prior):
        seen["prior"] = [f.insight_key for f in prior]
        return []

    facts = run_rules(snapshot(), th(), [Rule("second-rule", second, ("first-rule",)), Rule("first-rule", first)])
    assert seen["prior"] == [f"first-rule:athlete:{AS_OF.isoformat()}"] and len(facts) == 1


def test_engine_rejects_malformed_or_duplicate_facts():
    bad = make_fact("r", "athlete", AS_OF, "observation", 1.0, "x", {}, "t")
    with pytest.raises(ValueError, match="emitted a fact"):
        run_rules(snapshot(), th(), [Rule("other", lambda s, t, p: [bad])])
    broken = dataclasses.replace(bad, insight_key="nonsense")
    with pytest.raises(ValueError, match="insight_key"):
        run_rules(snapshot(), th(), [Rule("r", lambda s, t, p: [broken])])
    with pytest.raises(ValueError, match="duplicate"):
        run_rules(snapshot(), th(), [Rule("r", lambda s, t, p: [bad, bad])])
    odd = dataclasses.replace(bad, kind="alarm")
    with pytest.raises(ValueError, match="kind"):
        run_rules(snapshot(), th(), [Rule("r", lambda s, t, p: [odd])])


def test_insight_fact_has_exactly_the_ad8_fields_and_no_severity():
    assert [f.name for f in dataclasses.fields(InsightFact)] == [
        "insight_key", "rule_id", "subject", "period", "kind", "number", "unit", "evidence", "template_id",
    ]
    assert KINDS == ("observation", "attaboy", "check-reading")


# ---- a rich snapshot that fires many rules ----

START = date(2026, 9, 16)  # fixed so that episode keys do not depend on as_of


def _rich(as_of):
    n_days = (as_of - START).days + 1
    runs = (
        run("old", AS_OF - 20 * D, 10.0),
        run("spike", AS_OF - 2 * D, 12.5),
        run("drift", AS_OF - D, 10.0, 60, minutes=minutes(60, hr=140.0, hr2=156.0, split=35)),
    )
    rhr_vals = [57.0] * ((as_of - AS_OF).days + 5)
    snap = snapshot(
        as_of=as_of,
        runs=runs,
        resting_hr=daily(AS_OF - 4 * D, rhr_vals),
        rhr_baseline=baseline(50.0, 2.0, 30),
        hrv_sdnn_ms=daily(date(2026, 10, 15), [50.0] * ((as_of - date(2026, 10, 15)).days + 1)),
        hrv_baseline=baseline(math.log(60.0), 0.1, 45),
        days=day_classes(START, as_of, hard={as_of - D, as_of}),
        training_state=TrainingStateDay(as_of, "Building", "Building", date(2026, 10, 20), 5.5, -8.0),
        history_start=START,
    )
    return snap


def _keys(facts):
    return [f.insight_key for f in facts]


def test_rich_snapshot_fires_the_expected_rules():
    facts = run_rules(_rich(AS_OF), th())
    rules_fired = {f.rule_id for f in facts}
    assert {"long-run-spike", "cardiac-drift", "resting-hr", "hrv", "hard-day-stacking", "no-rest-day", "training-state"} <= rules_fired
    hrv_fact = next(f for f in facts if f.rule_id == "hrv")
    assert hrv_fact.template_id == "hrv-below-rhr"  # the engine passed the resting-hr fact as prior


def test_keys_are_stable_across_two_engine_runs():
    a = run_rules(_rich(AS_OF), th())
    b = run_rules(_rich(AS_OF), th())
    assert a == b and _keys(a) == _keys(b)
    assert len(set(_keys(a))) == len(a)


def test_keys_of_ongoing_conditions_do_not_change_the_next_day():
    ongoing = {"resting-hr", "hrv", "no-rest-day", "training-state"}
    today = {f.insight_key for f in run_rules(_rich(AS_OF), th()) if f.rule_id in ongoing}
    tomorrow = {f.insight_key for f in run_rules(_rich(AS_OF + D), th()) if f.rule_id in ongoing}
    assert today and today == tomorrow


def test_per_run_keys_do_not_depend_on_as_of():
    today = {f.insight_key for f in run_rules(_rich(AS_OF), th()) if f.rule_id in ("long-run-spike", "cardiac-drift")}
    tomorrow = {f.insight_key for f in run_rules(_rich(AS_OF + D), th()) if f.rule_id in ("long-run-spike", "cardiac-drift")}
    assert today == tomorrow and len(today) == 2


def test_every_fact_is_well_formed_and_carries_rule_data_and_note():
    for f in run_rules(_rich(AS_OF), th()):
        assert is_valid_key(f.insight_key) and f.insight_key == f"{f.rule_id}:{f.subject}:{f.period}"
        assert f.kind in KINDS and isinstance(f.number, float) and f.unit
        assert set(f.evidence) == {"rule", "data", "note"} and f.evidence["rule"] == f.rule_id and f.evidence["note"]
        assert f.template_id in TEMPLATES
        json.dumps(f.evidence)  # stored as JSON with the feedback snapshot (AD-6)


def test_engine_is_independent_of_rule_registration_order():
    snap = _rich(AS_OF)
    forward = run_rules(snap, th(), registered_rules())
    backward = run_rules(snap, th(), list(reversed(registered_rules())))
    assert forward == backward


# ---- thresholds ----

def test_thresholds_load_from_toml_and_overrides_are_validated():
    t = load_thresholds({"long-run-spike": {"jump_pct": 20.0}})
    assert t.rule("long-run-spike")["jump_pct"] == 20.0 and th().rule("long-run-spike")["jump_pct"] == 10.0
    with pytest.raises(ValueError, match="unknown threshold"):
        load_thresholds({"long-run-spike": {"jmp_pct": 1}})
    with pytest.raises(ValueError, match="unknown thresholds section"):
        load_thresholds({"nope": {"x": 1}})


def test_every_rule_has_a_thresholds_section():
    t = th()
    for r in registered_rules():
        assert t.rule(r.rule_id)
    assert {"engine", "load", "days"} <= set(t.as_dict())


def test_rules_hold_no_numeric_thresholds_of_their_own():
    """Thresholds live only in config/thresholds.toml: rule modules contain no tunable numeric literals."""
    from pathlib import Path

    import strydr.pipeline.insights.rules as pkg

    allowed = {"0", "1", "2", "3", "0.0", "1.0", "100.0", "5", "6", "7", "60", "1000.0"}
    for path in Path(pkg.__file__).parent.glob("*.py"):
        text = re.sub(r'""".*?"""|"[^"\n]*"', "", path.read_text(), flags=re.S)
        text = re.sub(r"#.*", "", text)
        found = set(re.findall(r"(?<![\w.\[])\d+\.?\d*(?![\w])", text))
        assert found <= allowed, f"{path.name}: {found - allowed}"


# ---- templates ----

DATA = {
    "distance_m": 12000, "longest_prior_m": 10000, "window_days": 30, "week_distance_m": 30000, "avg_prior_weeks_m": 20000,
    "baseline_weeks": 4, "period": "2026-09", "min_runs_per_week": 3, "easy_ceiling_bpm": 152, "recent_days": 14,
    "hr_higher_bpm": 4.0, "duration_s": 3600, "temperature_c": 26.0, "last_days_bpm": [56, 57, 58], "band_bpm": [135, 145],
    "form_pct": -31.0, "dew_point_c": 18.0, "adjusted_pace_s_per_unit": 560, "dew_split_c": 15.0, "warm_runs": 7,
    "cool_runs": 9, "under_usual_h": 1.4, "short_runs": 6, "good_runs": 8,
    "events": [{"event": "x", "label": "5k", "distance_m": 5000, "time_s": 1500, "milestone": 100, "unit": "km"}],
}
UNITS = {"attaboys-streaks-best-effort": ("s", 1500.0), "attaboys-streaks-longest-run": ("m", 21097.0),
         "attaboys-streaks-record-week": ("m", 45000.0), "attaboys-streaks-record-month": ("m", 180000.0),
         "attaboys-streaks-milestone": ("km", 100.0), "heat-adjusted-pace": ("s", 21.0), "hill-adjusted-pace": ("s", 14.0)}


def _example(tid):
    t = TEMPLATES[tid]
    unit, number = UNITS.get(tid, ("%", 7.5))
    return make_fact(t.rule_id, "athlete", AS_OF, "observation", number, unit, make_evidence(t.rule_id, DATA, "note"), tid)


def test_there_is_a_template_for_every_template_id_rules_can_emit():
    emitted = {f.template_id for f in run_rules(_rich(AS_OF), th())}
    assert emitted <= set(TEMPLATES)
    assert {t.rule_id for t in TEMPLATES.values()} == TIER_1 | TIER_2


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
@pytest.mark.parametrize("units", ["km", "mi"])
def test_template_lint(tid, units):
    fact = _example(tid)
    text = render(fact, units)
    low = text.lower()
    assert "!" not in text
    for term in BANNED_TERMS:
        assert term not in low, f"{tid}: banned {term!r} in {text!r}"
    assert re.search(r"\byou(r)?\b", low), f"{tid}: not second person"
    assert text.endswith(".") and not re.search(r"[.!?]\s", text), f"{tid}: not exactly one sentence: {text!r}"
    f = base_fields(fact, units)
    assert any(f[k] in text for k in ("n", "n_abs", "n_signed")), f"{tid}: headline number missing"
    assert "{" not in text and "}" not in text


def test_causal_wording_uses_associated_with():
    for tid in ("resting-hr-elevated", "hrv-below", "cardiac-drift-notable-heat", "long-run-spike"):
        assert "associated with" in render(_example(tid), "km")


def test_render_uses_the_runners_units():
    f = _example("long-run-spike")
    assert "12 km" in render(f, "km") and "10 km" in render(f, "km")
    assert "7.5 mi" in render(f, "mi") and "6.2 mi" in render(f, "mi")
    assert render(f, "km") == render(f, "km")


def test_render_formats_times_and_milestones():
    assert "25:00" in render(_example("attaboys-streaks-best-effort"), "km")
    assert "100 km" in render(_example("attaboys-streaks-milestone"), "km")
    assert "1 mile" not in render(_example("attaboys-streaks-best-effort"), "km")  # label comes from the fact, 5k here
    assert "5 km" in render(_example("attaboys-streaks-best-effort"), "mi")  # standard distances keep their name


def test_render_rejects_unknown_template():
    f = dataclasses.replace(_example("no-rest-day"), template_id="made-up")
    with pytest.raises(KeyError):
        render(f, "km")


def test_rendered_rich_facts_in_both_units_pass_the_lint():
    for f in run_rules(_rich(AS_OF), th()):
        for units in ("km", "mi"):
            text = render(f, units)
            assert "!" not in text and not any(t in text.lower() for t in BANNED_TERMS)

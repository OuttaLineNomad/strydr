"""CAP-16 / AD-10: the run context payload, its formatting and its number allow-list. Everything here is invented."""
import re
from datetime import date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from strydr.egress import RunContextPayload
from strydr.pipeline.phrasing import format as fmt
from strydr.pipeline.phrasing.run_context import allowed_numbers_run, build_run_context
from strydr.pipeline.phrasing.validate import validate
from strydr.store import models

from helpers import add_run, recompute_now

AS_OF = "2026-10-26"
NOTE_TEXT = "felt a twinge near the old bakery on Elm Street"
SLEEP = {"night_of": "2026-10-25", "total_h": 4.27, "deep_h": 0.5, "rem_h": 0.9, "core_h": 2.87, "awake_h": 0.4,
         "bedtime": "23:41", "wake": "04:57", "hours_before_run": 2.1, "efficiency_pct": 91.4, "deep_rem_pct": 33,
         "usual_h": 7.1, "vs_usual_h": -2.83, "quality": "short", "rhr_bpm": 58.0, "rhr_usual_bpm": 54.2,
         "hrv_ms": 41.0, "hrv_usual_ms": 47.0}
CONDITIONS = {"temp_c": 28.9, "humidity_pct": 60, "dew_point_c": 20.4, "apparent_c": 31.0, "wind_ms": 4.0,
              "wind_dir_deg": 225.0, "gust_ms": 7.0, "precip_mm_h": 0.0, "cloud_pct": 40.0, "temp_dew_sum_f": 152,
              "heat_adjust_pct": 4.5, "heat_adjusted_speed_mps": 3.1, "band": "oppressive", "windy": False,
              "rain": False, "sources": {"temperature": "apple", "wind": "open-meteo"}}


def _seed(engine, prior=3, route=True):
    for i in range(prior):
        add_run(engine, f"p{i}", datetime(2026, 10, 12 + 2 * i, 17), 40, 3.0 if route else 2.8 + 0.1 * i, hr=[148.0 + i] * 40, route=route)
    add_run(engine, "r", datetime(2026, 10, 22, 7, 30), 40, 3.0, hr=[152.0] * 40, route=route)
    recompute_now(engine, AS_OF)


def _patch(engine, wid="r", **cols):
    with Session(engine) as s:
        s.execute(update(models.WorkoutDetail).where(models.WorkoutDetail.workout_id == wid).values(**cols))
        s.commit()


def _facts(engine, n=2):
    with Session(engine) as s:
        gen = s.execute(select(models.CurrentGeneration.generation_id)).scalar_one()
        for i in range(n):
            s.add(models.InsightFact(
                generation_id=gen, insight_key=f"k{i}", rule_id="effort-by-sleep", subject="run/r", period="2026-W43",
                kind="observation", number=1.0, unit="%", evidence={}, template_id="t",
                text_template=f"Your effort was {10 + i}% higher on 4 hours of sleep.", phrase_hash="h",
                local_date="2026-10-22", week_id="2026-W43"))
        s.add(models.WorkoutNote(workout_id="r", text=NOTE_TEXT, rpe=6, updated_at=datetime(2026, 10, 22)))
        s.commit()


def _build(engine, units="mi", wid="r"):
    with Session(engine) as s:
        return build_run_context(s, wid, units, date.fromisoformat(AS_OF))


@pytest.fixture
def full(engine):
    _seed(engine)
    _patch(engine, conditions=CONDITIONS, sleep=SLEEP)
    _facts(engine)
    return engine


# ---- formatting: golden strings from web/src/lib/units.ts and sleep.ts ------------------------------------------------

def test_formatters_match_the_web():
    assert fmt.pace(3, "mi") == "8:56 /mi" and fmt.pace(4, "km") == "4:10 /km" and fmt.pace(0, "km") is None
    assert fmt.pace_from_s(844, "mi") == "14:04 /mi"
    assert fmt.clock(3725) == "1:02:05" and fmt.clock(59.6) == "1:00" and fmt.duration(3733) == "1:02:13"
    assert fmt.distance(8046.72, "mi") == "5.0 mi" and fmt.distance(8046.72, "km", 2) == "8.05 km"
    assert fmt.elevation(100, "mi") == "328 ft" and fmt.elevation(100, "km") == "100 m"
    assert fmt.elevation(36.576, "mi", signed=True) == "+120 ft" and fmt.elevation(-3, "km", signed=True) == "−3 m"
    assert fmt.temperature(29, "mi") == "84°F" and fmt.temperature(28.9, "km") == "29°C"
    assert fmt.wind(4, "mi") == "9 mph" and fmt.wind(4, "km") == "14 km/h"
    assert fmt.hours(4.27) == "4h 16m" and fmt.hours(4.1) == "4h 06m" and fmt.hours(0.5) == "30m"
    assert fmt.signed_hours(-2.83) == "−2h 50m" and fmt.pace_delta(-8, "mi") == "−0:08 /mi"
    assert fmt.bpm(151.5) == "152 bpm" and fmt.percent(61.6) == "62%"
    assert fmt.js_round(2.5) == 3 and fmt.js_round(0.5) == 1  # halves go up, as Math.round


# ---- the builder ------------------------------------------------------------------------------------------------------

def test_full_run_imperial(full):
    p = _build(full)
    assert RunContextPayload.model_validate_json(p.model_dump_json()) == p
    assert p.units == "mi"
    assert p.run["avg_pace"] == "8:56 /mi" and p.run["time_band"] == "morning" and p.run["when"] == "4 days ago"
    assert p.run["rpe"] == "6" and p.run["avg_hr"] == "152 bpm" and p.run["type"] == "run"
    assert p.conditions["temperature"] == "84°F" and p.conditions["wind"] == "9 mph"
    assert p.conditions["band"] == "oppressive" and p.conditions["heat_adjustment"] == "4.5%"
    assert p.sleep["hours"] == "4h 16m" and p.sleep["quality"] == "short" and p.sleep["vs_usual"] == "−2h 50m"
    assert p.sleep["rhr_vs_usual"] == "+4 bpm" and p.sleep["hrv_vs_usual"] == "−6 ms"
    assert {"run_load", "load_7_days", "fitness", "fatigue", "form", "runs_this_week"} <= set(p.training)
    assert p.training["days_since_last_run"] == "6" and p.training["runs_this_week"] == "1"
    assert p.comparison["similar_runs"] == "3"
    assert {"usual_pace", "usual_hr", "beats_per_km", "usual_beats_per_km"} <= set(p.comparison)
    assert p.comparison["pace"] == p.run["avg_pace"]
    assert len(p.splits) >= 4 and all("pace" in s for s in p.splits)
    assert [i.rule_id for i in p.insights] == ["effort-by-sleep"] * 2


def test_metric_run(full):
    p = _build(full, "km")
    assert p.run["avg_pace"].endswith(" /km") and p.run["distance"].endswith(" km")
    assert p.conditions["temperature"] == "29°C" and p.conditions["wind"] == "14 km/h"
    assert p.run["elevation_gain"] == "30 m"
    assert not any("/mi" in v or "°F" in v or "mph" in v for v in _strings(p))


def test_bare_run(engine):
    add_run(engine, "r", datetime(2026, 10, 22, 19, 0), 30, 3.0, hr=None, route=False)
    recompute_now(engine, AS_OF)
    p = _build(engine)
    assert "avg_hr" not in p.run and "max_hr" not in p.run and "rpe" not in p.run
    assert p.run["time_band"] == "evening" and "when" in p.run
    assert not (p.terrain or p.conditions or p.sleep or p.comparison or p.insights)
    assert "days_since_last_run" not in p.training and p.training["runs_this_week"] == "1"


def test_one_similar_run_gives_no_comparison(engine):
    _seed(engine, prior=1)
    assert _build(engine).comparison == {}


def test_similar_by_distance_when_there_is_no_route(engine):
    _seed(engine, prior=3, route=False)
    assert _build(engine).comparison["similar_runs"] == "3"  # 40 min at 2.8-3.0 m/s: within 20% of 7.2 km


def test_unknown_workout(engine):
    assert _build(engine, wid="nope") is None


def test_privacy(full):
    p = _build(full)
    text = p.model_dump_json()
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text) and not re.search(r"\d{1,2}:\d{2}\s?(am|pm)", text, re.I)
    assert not re.search(r"\d+\.\d{4,}", text)
    for secret in (NOTE_TEXT, "Elm", "bakery", "23:41", "04:57", "225", "open-meteo", "apple"):
        assert secret not in text
    assert not re.search(r'"(wind_dir\w*|bedtime|wake|night_of|hours_before_run|sources)"', text)
    assert p.run["rpe"] == "6"


def test_hostile_value_is_dropped_by_the_builder_and_refused_by_the_model(engine):
    _seed(engine)
    _patch(engine, sleep={**SLEEP, "quality": "short!"}, conditions={**CONDITIONS, "band": "Synthetic Watch"})
    p = _build(engine)
    assert "quality" not in p.sleep and "band" not in p.conditions and "hours" in p.sleep
    with pytest.raises(ValidationError):
        RunContextPayload(units="mi", run={"type": "run!"})
    with pytest.raises(ValidationError):
        RunContextPayload(units="mi", sleep={"quality": "Synthetic Watch"})


# ---- the allow-list --------------------------------------------------------------------------------------------------

def test_off_context_number_is_rejected_and_on_context_passes(full):
    p = _build(full)
    allowed = allowed_numbers_run(p)
    assert "8:56" in allowed and "84" in allowed and "-2" in allowed
    assert validate("You ran 9:10 /mi.", allowed) is None
    assert validate("You ran 8:56 /mi in 84°F heat.", allowed) == "You ran 8:56 /mi in 84°F heat."
    assert validate("About eight hours.", allowed) is None  # spelled out


def _strings(p):
    out = list(p.run.values()) + list(p.terrain.values()) + list(p.conditions.values()) + list(p.sleep.values())
    out += list(p.training.values()) + list(p.comparison.values())
    return out + [v for s in p.splits for v in s.values()]


# ---- exact values --------------------------------------------------------------------------------------------------

def test_formatters_refuse_non_finite_input():
    nan, inf = float("nan"), float("inf")
    for f in (fmt.pace, fmt.distance, fmt.elevation, fmt.temperature, fmt.wind):
        assert f(nan, "mi") is None and f(inf, "km") is None
    for f in (fmt.pace_from_s, fmt.relief_per_unit, fmt.pace_delta):
        assert f(nan, "mi") is None and f(-inf, "km") is None
    for f in (fmt.duration, fmt.hours, fmt.signed_hours, fmt.bpm, fmt.percent, fmt.whole, fmt.signed_whole):
        assert f(nan) is None and f(inf) is None
    assert fmt.elevation(nan, "mi", signed=True) is None


def test_relief_per_unit_golden():
    assert fmt.relief_per_unit(12.0, "km") == "12 m/km" and fmt.relief_per_unit(12.0, "mi") == "63 ft/mi"


def test_terrain_conditions_and_sleep_exact(full):
    _patch(full, gap={"gap_speed_mps": 3.2, "relief_m": 36.576, "relief_m_per_km": 12.0, "hilly": True})
    p = _build(full)
    assert p.terrain == {"gap_pace": "8:23 /mi", "relief": "120 ft", "relief_per_distance": "63 ft/mi", "hilly": "yes"}
    m = _build(full, "km")
    assert m.terrain == {"gap_pace": "5:13 /km", "relief": "37 m", "relief_per_distance": "12 m/km", "hilly": "yes"}
    c = p.conditions
    assert (c["feels_like"], c["humidity"], c["dew_point"], c["cloud"], c["rain"]) == (
        "88\u00b0F", "60%", "69\u00b0F", "40%", "Dry")
    assert (p.sleep["usual_sleep"], p.sleep["usual_rhr"], p.sleep["usual_hrv"]) == ("7h 06m", "54 bpm", "47 ms")


def test_rain_and_a_real_zero_heat_adjustment(engine):
    _seed(engine)
    _patch(engine, conditions={**CONDITIONS, "rain": True, "precip_mm_h": 1.2, "heat_adjust_pct": 0.0})
    c = _build(engine).conditions
    assert c["rain"] == "1.2 mm/h" and c["heat_adjustment"] == "0.0%"


def test_vs_usual_deltas_use_the_shown_values(engine):
    _seed(engine)
    _patch(engine, sleep={**SLEEP, "rhr_bpm": 58.4, "rhr_usual_bpm": 54.5, "hrv_ms": 40.6, "hrv_usual_ms": 47.4})
    z = _build(engine).sleep
    assert (z["morning_rhr"], z["usual_rhr"], z["rhr_vs_usual"]) == ("58 bpm", "55 bpm", "+3 bpm")
    assert (z["morning_hrv"], z["usual_hrv"], z["hrv_vs_usual"]) == ("41 ms", "47 ms", "\u22126 ms")


def test_partial_split_has_a_distance_and_whole_ones_do_not(full):
    sp = _build(full).splits
    assert sp[-1]["distance"] == "0.47 mi" and all("distance" not in x for x in sp[:-1])
    assert sp[0]["split"] == "1" and sp[-1]["split"] == str(len(sp))


def test_training_numbers_match_the_daily_load_rows(full):
    with Session(full) as s:
        rows = {d.local_date: d for d in s.execute(select(models.DailyLoad)).scalars()}
    window = [d for k, d in rows.items() if "2026-10-16" <= k <= "2026-10-22"]
    t = _build(full).training
    assert t["load_7_days"] == str(fmt.js_round(sum(d.load for d in window)))
    assert t["form"] == fmt.signed_whole(rows["2026-10-22"].form)
    assert t["fitness"] == str(fmt.js_round(rows["2026-10-22"].fitness))


def test_similar_runs_exclude_decoys(engine):
    for i in range(3):
        add_run(engine, f"p{i}", datetime(2026, 10, 12 + 2 * i, 17), 40, 3.0, hr=[148.0 + i] * 40)
    add_run(engine, "far", datetime(2026, 10, 19, 17), 80, 3.0, hr=[140.0] * 80, route=False)  # 2x distance
    add_run(engine, "elsewhere", datetime(2026, 10, 20, 17), 40, 2.0, hr=[130.0] * 40, origin=(40.0, -3.0))
    add_run(engine, "r", datetime(2026, 10, 22, 7, 30), 40, 3.0, hr=[152.0] * 40)
    add_run(engine, "later", datetime(2026, 10, 24, 7), 40, 3.0, hr=[100.0] * 40)
    recompute_now(engine, AS_OF)
    c = _build(engine).comparison
    assert c["similar_runs"] == "3" and c["usual_pace"] == "8:56 /mi" and c["pace"] == "8:56 /mi"
    assert c["usual_hr"] == "149 bpm" and c["hr"] == "152 bpm"


def test_route_with_one_prior_falls_back_to_distance(engine):
    add_run(engine, "p0", datetime(2026, 10, 12, 17), 40, 3.0, hr=[148.0] * 40)
    add_run(engine, "d1", datetime(2026, 10, 14, 17), 40, 2.8, hr=[148.0] * 40, route=False)
    add_run(engine, "d2", datetime(2026, 10, 16, 17), 40, 2.8, hr=[148.0] * 40, route=False)
    add_run(engine, "far", datetime(2026, 10, 17, 17), 80, 3.0, hr=[148.0] * 80, route=False)
    add_run(engine, "r", datetime(2026, 10, 22, 7, 30), 40, 3.0, hr=[152.0] * 40)
    recompute_now(engine, AS_OF)
    with Session(engine) as s:
        assert s.execute(select(models.WorkoutRoute.route_key).where(models.WorkoutRoute.workout_id == "r")).first()
    c = _build(engine).comparison
    assert c["similar_runs"] == "3" and c["usual_pace"] == "9:22 /mi"


def test_insights_cap_order_and_unsafe_sentence(engine):
    _seed(engine, prior=0)
    with Session(engine) as s:
        gen = s.execute(select(models.CurrentGeneration.generation_id)).scalar_one()
        for i in range(14):
            text = "Ran 52.123 km on Oct 22." if i == 9 else f"Fact {i} is {i}% up."
            s.add(models.InsightFact(
                generation_id=gen, insight_key=f"k{i:02d}", rule_id="weekly-ramp", subject="run/r", period="2026-W43",
                kind="observation", number=1.0, unit="%", evidence={}, template_id="t", text_template=text,
                phrase_hash="h", local_date=f"2026-10-{i + 1:02d}", week_id="2026-W43"))
        s.commit()
    got = [i.sentence for i in _build(engine).insights]
    want = [f"Fact {i} is {i}% up." for i in range(13, -1, -1) if i != 9][:12]
    assert got == want and len(got) == 12 and not any("52.123" in g for g in got)


def test_a_word_value_outside_its_closed_set_is_refused():
    for group, key, val in (("sleep", "quality", "km"), ("run", "type", "km"), ("conditions", "band", "restless"),
                            ("training", "state", "good"), ("terrain", "hilly", "maybe"), ("run", "time_band", "noon"),
                            ("conditions", "rain", "hot"), ("sleep", "vs_usual", "good")):
        with pytest.raises(ValidationError):
            RunContextPayload(units="mi", **{group: {key: val}})

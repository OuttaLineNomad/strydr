"""Every insight template (AD-8). One sentence, second person, one headline number `{n}`.

Wording rules (FR-21/21a): no "!", "associated with" and never causal verbs, no diagnostic, injury-risk,
calorie or weight framing. Attaboys never discourage rest. `test_templates` lints all of this.
"""
from ._format import Template, carry_text, clock, dist

_LABELS = {"400m": "400 m", "1k": "1 km", "1mi": "1 mile", "5k": "5 km", "10k": "10 km", "half": "half-marathon", "marathon": "marathon"}


def _long_run(f, u):
    return {"dist": dist(f.evidence["data"]["distance_m"], u), "longest": dist(f.evidence["data"]["longest_prior_m"], u)}


def _ramp(f, u):
    d = f.evidence["data"]
    return {"week": dist(d["week_distance_m"], u), "avg": dist(d["avg_prior_weeks_m"], u)}


def _effort(f, u):
    return {"label": _LABELS.get(f.evidence["data"]["events"][0]["label"], f.evidence["data"]["events"][0]["label"])}


def _milestone(f, u):
    return {"unit": f.evidence["data"]["events"][0]["unit"]}


def _month(f, u):
    return {"start": f.evidence["data"]["period"] + "-01"}


def _hr_centre(f, u):
    lo, hi = f.evidence["data"]["band_bpm"]
    return {"hr": round((lo + hi) / 2)}


def _drift(f, u):
    d = f.evidence["data"]
    return {"minutes": round(d["duration_s"] / 60), "temp": round(d["temperature_c"]) if d["temperature_c"] is not None else ""}


def _carry(f, u):
    return {"carry": carry_text(f.evidence["data"]["carried_kg"], u)}


def _drift_carry(f, u):
    return {**_drift(f, u), **_carry(f, u)}


def _stack_carry(f, u):
    n = len(f.evidence["data"]["carried_days"])
    return {"carried": "one of them a carried run" if n == 1 else f"{n} of them carried runs"}


def _rhr(f, u):
    return {"days": len(f.evidence["data"]["last_days_bpm"])}


def _form(f, u):
    form = f.evidence["data"]["form_pct"]
    return {"form": "n/a" if form is None else f"{form:.0f}"}


def _temp(c, u):
    return f"{round(c * 9 / 5 + 32)} °F" if u == "mi" else f"{round(c)} °C"


def _adjusted(f, u):
    d = f.evidence["data"]
    out = {"unit": "mile" if u == "mi" else "km", "adj": clock(d["adjusted_pace_s_per_unit"])}
    if d.get("dew_point_c") is not None:
        out["dew"] = _temp(d["dew_point_c"], u)
    out["air"] = {"oppressive": "Very hot, humid air", "hot": "Hot, humid air"}.get(d.get("band"), "Warm air")
    return out


def _hours(h):
    m = round(h * 60)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _sleep(f, u):
    d = f.evidence["data"]
    return {"under": _hours(d["under_usual_h"])} if d.get("under_usual_h") is not None else {}


def _dew_split(f, u):
    return {"dew": _temp(f.evidence["data"]["dew_split_c"], u)}


_T = [
    Template("long-run-spike", "long-run-spike",
             "This run ({dist}) is {n}% longer than your longest in the last {d[window_days]} days ({longest}), and sudden jumps in distance are associated with slower recovery.",
             _long_run),
    Template("weekly-ramp", "weekly-ramp",
             "Your running this week is {n}% above your {d[baseline_weeks]}-week average ({week} against {avg}), shown as context only.",
             _ramp),
    Template("attaboys-streaks-best-effort", "attaboys-streaks", "Your {label} time of {n} is the fastest you have run.", _effort),
    Template("attaboys-streaks-longest-run", "attaboys-streaks", "At {n}, this is your longest run so far."),
    Template("attaboys-streaks-milestone", "attaboys-streaks", "You have now covered {n} {unit} in total.", _milestone),
    Template("attaboys-streaks-record-week", "attaboys-streaks", "Your {n} of running this week is your highest weekly distance so far."),
    Template("attaboys-streaks-record-month", "attaboys-streaks",
             "Your {n} of running in the month starting {start} is your highest monthly distance so far.", _month),
    Template("attaboys-streaks-streak", "attaboys-streaks",
             "You have run {d[min_runs_per_week]} or more times a week for {n} weeks running, with a missed week allowed now and then."),
    Template("intensity-mix", "intensity-mix",
             "Only {n}% of your running time over the last {d[window_days]} days was at an easy heart rate, while 80/20 is a common pattern among endurance athletes."),
    Template("easy-creep-ceiling", "easy-creep",
             "{n}% of your easy-intended runs in the last {d[recent_days]} days averaged above your easy ceiling of {d[easy_ceiling_bpm]} bpm."),
    Template("easy-creep-pace", "easy-creep",
             "Your easy runs are {n}% faster than your 8-week norm, at an average heart rate {d[hr_higher_bpm]} bpm higher."),
    Template("cardiac-drift-notable", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this run, and heat and hills can skew drift."),
    Template("cardiac-drift-high", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this run, which is high, and heat, hills and hydration can all skew drift."),
    Template("cardiac-drift-notable-heat", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this warm run ({temp} °C), and heat is associated with more drift.", _drift),
    Template("cardiac-drift-high-heat", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this warm run ({temp} °C), which is high, and heat is associated with more drift.", _drift),
    Template("cardiac-drift-notable-carry", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this run carrying {carry}, and the extra load is associated with more drift, though heat and hills can skew drift too.", _drift_carry),
    Template("cardiac-drift-high-carry", "cardiac-drift",
             "Your pace-to-heart-rate ratio drifted {n}% over this run carrying {carry}, which is high, and the extra load is associated with more drift, though heat and hills can skew drift too.",
             _drift_carry),
    Template("cardiac-drift-solid-carry", "cardiac-drift",
             "Carrying {carry}, your pace held steady against your heart rate for {minutes} minutes, drifting only {n}%, though heat and hills can skew drift.", _drift_carry),
    Template("carry-run", "carry", "You ran this one carrying {carry}.", _carry),
    Template("pace-at-hr-faster-carry", "pace-at-fixed-hr",
             "At about {hr} bpm, your carried runs are {n}% faster than in the 4 weeks before.", _hr_centre),
    Template("pace-at-hr-slower-carry", "pace-at-fixed-hr",
             "At about {hr} bpm, your carried runs are {n}% slower than in the 4 weeks before, and heat and tiredness can move it too.",
             _hr_centre),
    Template("easy-creep-ceiling-carry", "easy-creep",
             "{n}% of your easy-intended carried runs in the last {d[recent_days]} days averaged above your easy ceiling of {d[easy_ceiling_bpm]} bpm."),
    Template("easy-creep-pace-carry", "easy-creep",
             "Your easy carried runs are {n}% faster than your 8-week norm for carried runs, at an average heart rate {d[hr_higher_bpm]} bpm higher."),
    Template("pace-by-conditions-carry", "pace-by-conditions",
             "Over the last {d[window_days]} days, your easy carried runs with a dew point of {dew} or more were typically {n}% slower than your cooler ones ({d[warm_runs]} against {d[cool_runs]} runs).",
             _dew_split),
    Template("hard-day-stacking-consecutive-carry", "hard-day-stacking",
             "You have had {n} hard days in the last {d[window_days]} days, including two in a row, and {carried}.", _stack_carry),
    Template("hard-day-stacking-window-carry", "hard-day-stacking",
             "You have had {n} hard days in the last {d[window_days]} days, and {carried}.", _stack_carry),
    Template("cardiac-drift-solid", "cardiac-drift",
             "Your pace held steady against your heart rate for {minutes} minutes, drifting only {n}%, though heat and hills can skew drift.", _drift),
    Template("resting-hr-elevated", "resting-hr",
             "Your resting heart rate has been about {n} bpm above your 30-day norm for {days} days, which is associated with incomplete recovery, heat or poor sleep.",
             _rhr),
    Template("resting-hr-check", "resting-hr",
             "Check this reading: your resting heart rate of {n} bpm is unusual for you, and a device error is possible."),
    Template("hrv-below", "hrv",
             "Your 7-day HRV is {n}% below your usual level, which is associated with accumulated fatigue or poor sleep, though Apple Watch HRV is noisy."),
    Template("hrv-below-rhr", "hrv",
             "Your 7-day HRV is {n}% below your usual level and your resting heart rate is also high, though Apple Watch HRV is noisy."),
    Template("pace-at-hr-faster", "pace-at-fixed-hr",
             "At about {hr} bpm, your pace is {n}% faster than in the 4 weeks before.", _hr_centre),
    Template("pace-at-hr-slower", "pace-at-fixed-hr",
             "At about {hr} bpm, your pace is {n}% slower than in the 4 weeks before, and heat and tiredness can move it too.", _hr_centre),
    Template("heat-adjusted-pace", "heat-adjusted-pace",
             "{air} (dew point {dew}) is associated with about {n} per {unit} of your pace on this run, an estimated {adj} per {unit} in cool conditions.",
             _adjusted),
    Template("hill-adjusted-pace", "hill-adjusted-pace",
             "The climbs on this run are associated with about {n} per {unit} of your pace, and adjusted for grade it was {adj} per {unit}.",
             _adjusted),
    Template("pace-by-conditions", "pace-by-conditions",
             "Over the last {d[window_days]} days, your easy runs with a dew point of {dew} or more were typically {n}% slower than your cooler ones ({d[warm_runs]} against {d[cool_runs]} runs).",
             _dew_split),
    Template("short-sleep-run", "short-sleep-run",
             "You slept {n} hours the night before this run, {under} under your usual, and short sleep is associated with a higher heart rate at the same pace.",
             _sleep),
    Template("short-sleep-run-no-usual", "short-sleep-run",
             "You slept {n} hours the night before this run, and short sleep is associated with a higher heart rate at the same pace."),
    Template("effort-by-sleep", "effort-by-sleep",
             "Over the last {d[window_days]} days, your easy runs after short nights took {n}% more heartbeats per kilometre than after good nights ({d[short_runs]} against {d[good_runs]} runs)."),
    Template("hard-day-stacking-consecutive", "hard-day-stacking",
             "You have had {n} hard days in the last {d[window_days]} days, including two in a row."),
    Template("hard-day-stacking-window", "hard-day-stacking", "You have had {n} hard days in the last {d[window_days]} days."),
    Template("hard-day-stacking-monotony", "hard-day-stacking",
             "Your daily load has varied very little this week (monotony {n}), and mixing harder and easier days is a common pattern."),
    Template("no-rest-day", "no-rest-day",
             "You have gone {n} days without a rest day, and many plans include a lighter day each week."),
    Template("training-state-building", "training-state",
             "Your training state is Building: your fitness is up {n_abs}% over the last 7 days."),
    Template("training-state-holding", "training-state",
             "Your training state is Holding: your fitness changed {n_signed}% over the last 7 days."),
    Template("training-state-easing", "training-state",
             "Your training state is Easing: your fitness is down {n_abs}% over the last 7 days."),
    Template("training-state-overreaching", "training-state",
             "Your training state is Overreaching: your recent load is high relative to your fitness (fitness {n_signed}% over 7 days, form {form}%).", _form),
]

TEMPLATES = {t.template_id: t for t in _T}
assert len(TEMPLATES) == len(_T), "duplicate template_id"

"""Weekly home-workout streak (CAP-10). Pure: local dates in, a Streak out. Weeks are Monday to Sunday."""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

RECENT_WEEKS = 8


@dataclass(frozen=True)
class Streak:
    weeks: int
    this_week: bool
    last_streak: int
    recent: list[tuple[date, bool]]  # (week's Monday, counted), oldest first, the current week last


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def streak(local_dates: Iterable[date], today: date) -> Streak:
    counted = {week_start(d) for d in local_dates}
    this = week_start(today)
    this_week = this in counted
    end = this if this_week else this - timedelta(weeks=1)  # the open week never breaks the chain

    def run_ending(at: date) -> int:
        n = 0
        while at in counted:
            n += 1
            at -= timedelta(weeks=1)
        return n

    weeks = run_ending(end)
    if weeks:
        last = weeks
    else:  # broken: the most recent run of counted weeks, if any
        past = [w for w in counted if w <= this]
        last = run_ending(max(past)) if past else 0
    recent = [(this - timedelta(weeks=i), (this - timedelta(weeks=i)) in counted) for i in range(RECENT_WEEKS - 1, -1, -1)]
    return Streak(weeks, this_week, last, recent)


# --- Strength score (CAP-12) ---------------------------------------------------------------------------------------
BELL_FLOOR_KG = 0.5
EFFORT_STEP = 0.05


@dataclass(frozen=True)
class ScoreInput:
    """What a session's score needs, as plain values: its own plan snapshot, the bell it used, the counts and effort."""
    plan: dict
    weight_kg: float | None
    rounds_done: int
    partial_moves: int
    fell_short: list
    short_reps: dict | None
    active_s: int
    effort: float | None


def session_rates(plan: dict, weight_kg: float | None, rounds_done: int, partial_moves: int,
                  fell_short: list | None, short_reps: dict | None, active_s: int) -> dict[str, float] | None:
    """Work per active minute for each move name: summed (amount x bell kg). None when there is no active time."""
    moves = plan.get("moves") or []
    if active_s <= 0 or not moves:
        return None
    base = next((m["weight_kg"] for m in moves if m.get("weight_kg") is not None), None)
    delta = weight_kg - base if weight_kg is not None and base is not None else 0.0
    work = [0.0] * len(moves)
    for i, m in enumerate(moves):
        done = rounds_done + (1 if i < partial_moves else 0)
        amount = m["reps"] if m.get("reps") is not None else m.get("seconds") or 0
        work[i] = done * amount  # amount summed over instances
    if plan.get("format") == "emom":  # a flagged minute with an answer counts the answer, not the target
        for minute in fell_short or []:
            answer = (short_reps or {}).get(str(minute))
            i = (minute - 1) % len(moves)
            target = moves[i].get("reps")
            if answer is not None and target is not None and work[i] > 0:
                work[i] = max(0.0, work[i] - max(0, target - answer))
    per_min = active_s / 60
    out: dict[str, float] = {}
    for i, m in enumerate(moves):
        kg = m.get("weight_kg")
        bell = max(BELL_FLOOR_KG, kg + delta) if kg is not None else 1.0
        out[m["name"]] = out.get(m["name"], 0.0) + work[i] * bell / per_min
    return out


def scores(sessions: Sequence[ScoreInput]) -> list[int | None]:
    """Strength scores for one plan's sessions, oldest first. The first is 100; a session with no active time, or no
    move in common with the first, is None."""
    rates = [session_rates(x.plan, x.weight_kg, x.rounds_done, x.partial_moves, x.fell_short, x.short_reps, x.active_s)
             for x in sessions]
    # the baseline is the earliest session with real work; earlier (empty) ones have no score
    base = next((i for i, r in enumerate(rates) if r and any(v > 0 for v in r.values())), None)
    if base is None:
        return [None] * len(sessions)
    first, first_rates = sessions[base], rates[base]
    out: list[int | None] = [None] * base + [100]
    for x, r in zip(sessions[base + 1:], rates[base + 1:]):
        ratios = [r[k] / first_rates[k] for k in r if r[k] > 0 and first_rates.get(k, 0) > 0] if r else []
        if not ratios:
            out.append(None)
            continue
        factor = 1 + EFFORT_STEP * (first.effort - x.effort) if first.effort is not None and x.effort is not None else 1.0
        out.append(round(100 * sum(ratios) / len(ratios) * factor))
    return out

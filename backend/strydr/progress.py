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
    set_rungs: dict | None = None  # ladder sets stepped down to an easier rung


def session_rates(plan: dict, weight_kg: float | None, rounds_done: int, partial_moves: int,
                  fell_short: list | None, short_reps: dict | None, active_s: int,
                  overrides: dict | None = None) -> dict[str, float] | None:
    """Work per active minute for each move name: summed (amount x bell kg). None when there is no active time."""
    moves = plan.get("moves") or []
    if active_s <= 0 or not moves:
        return None
    base = next((m["weight_kg"] for m in moves if m.get("weight_kg") is not None), None)
    delta = weight_kg - base if weight_kg is not None and base is not None else 0.0
    work = [0.0] * len(moves)
    rungs = set_rungs(plan, rounds_done, partial_moves, overrides)
    for i, m in enumerate(moves):
        done = rounds_done + (1 if i < partial_moves else 0)
        if i in rungs:  # a set stepped down to an easier rung is not work at the planned rung
            done = sum(1 for r in rungs[i] if r == m["rung"])
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
    move in common with an earlier one, is None. Each move name has its own baseline: the earliest scorable session that
    contains it (a ladder move at a new rung is a new name, so it starts afresh). A name's own baseline session does not
    count toward that session's mean; only names with an earlier baseline do."""
    rates = [session_rates(x.plan, x.weight_kg, x.rounds_done, x.partial_moves, x.fell_short, x.short_reps, x.active_s, x.set_rungs)
             for x in sessions]
    # the baseline is the earliest session with real work; earlier (empty) ones have no score
    base = next((i for i, r in enumerate(rates) if r and any(v > 0 for v in r.values())), None)
    if base is None:
        return [None] * len(sessions)
    first = sessions[base]
    name_base: dict[str, int] = {}  # move name -> index of its baseline session
    for i in range(base, len(sessions)):
        for k, v in (rates[i] or {}).items():
            if v > 0:
                name_base.setdefault(k, i)
    out: list[int | None] = [None] * base + [100]
    for j in range(base + 1, len(sessions)):
        x, r = sessions[j], rates[j]
        ratios = [r[k] / rates[name_base[k]][k] for k in r if r[k] > 0 and name_base[k] < j] if r else []
        if not ratios:
            out.append(None)
            continue
        factor = 1 + EFFORT_STEP * (first.effort - x.effort) if first.effort is not None and x.effort is not None else 1.0
        out.append(round(100 * sum(ratios) / len(ratios) * factor))
    return out


# --- Bodyweight ladders (CAP-13) -----------------------------------------------------------------------------------
# Mirrored in web/src/lib/ladders.ts; a test keeps the two equal.
LADDERS: dict[str, list[str]] = {
    "push-up": ["Wall", "Incline", "Knee", "Full", "Decline"],
    "pull-up": ["Negative", "Band-assisted", "Full"],
}
UNLOCK_SETS = 3
UNLOCK_REPS = 12


def rung_name(ladder: str, rung: int) -> str:
    """The display name of a rung: "Incline push-up"."""
    return f"{LADDERS[ladder][rung]} {ladder}"


@dataclass(frozen=True)
class LadderSet:
    move: int  # 0-based index in the snapshot
    instance: int  # 0-based: the n-th time the move was done
    ladder: str
    planned: int  # the snapshot's rung
    rung: int  # the rung actually done
    reps: int


def _instances(moves: Sequence[dict], rounds_done: int, partial_moves: int, i: int) -> int:
    return rounds_done + (1 if i < partial_moves else 0)


def set_rungs(plan: dict, rounds_done: int, partial_moves: int, overrides: dict[str, int] | None) -> dict[int, list[int]]:
    """For each ladder move (by index), the rung of each instance done: the snapshot's rung unless stepped down."""
    out: dict[int, list[int]] = {}
    for i, m in enumerate(plan.get("moves") or []):
        if m.get("ladder") is None or m.get("rung") is None:
            continue
        rungs = [m["rung"]] * _instances(plan["moves"], rounds_done, partial_moves, i)
        for k in range(len(rungs)):
            v = (overrides or {}).get(f"{i}:{k}")
            if v is not None:
                rungs[k] = v
        out[i] = rungs
    return out


def ladder_sets(plan: dict, rounds_done: int, partial_moves: int, fell_short: list | None, short_reps: dict | None,
                overrides: dict[str, int] | None) -> list[LadderSet]:
    """Every set of a ladder move in a session. Reps are the target, or the EMOM fell-short answer."""
    moves = plan.get("moves") or []
    n = len(moves)
    flagged = set(fell_short or []) if plan.get("format") == "emom" else set()
    out: list[LadderSet] = []
    for i, rungs in set_rungs(plan, rounds_done, partial_moves, overrides).items():
        m = moves[i]
        for k, rung in enumerate(rungs):
            reps = m.get("reps") or 0
            minute = k * n + i + 1  # EMOM: the minute this set was done in
            if minute in flagged and (short_reps or {}).get(str(minute)) is not None:
                reps = short_reps[str(minute)]
            out.append(LadderSet(i, k, m["ladder"], m["rung"], rung, reps))
    return out


def unlocks(moves: Sequence[dict], sets: Sequence[LadderSet]) -> list[dict]:
    """The ladder moves of `moves` (a plan's, in order) that the session's `sets` earn the next rung for: for a move at
    rung r, three or more sets on its ladder done at rung r with 12 or more reps each (wherever they sat in the
    session). The top rung never unlocks."""
    out: list[dict] = []
    for i, m in enumerate(moves):
        ladder, rung = m.get("ladder"), m.get("rung")
        if ladder is None or rung is None or rung + 1 >= len(LADDERS[ladder]):
            continue
        good = [s for s in sets if s.ladder == ladder and s.rung == rung and s.reps >= UNLOCK_REPS]
        if len(good) >= UNLOCK_SETS:
            out.append({"move_index": i, "ladder": ladder, "from_rung": rung, "to_rung": rung + 1})
    return out


def best_set(sets: Sequence[LadderSet], ladder: str) -> LadderSet | None:
    """The best set on a ladder: the highest rung, then the most reps."""
    mine = [s for s in sets if s.ladder == ladder]
    return max(mine, key=lambda s: (s.rung, s.reps)) if mine else None

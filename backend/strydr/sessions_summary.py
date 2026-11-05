"""The home-workout summary maths: which watch workout a session matches, and what its heart rate says per move,
per round and per zone. Pure functions over plain values; it reads nothing and imports nothing from the pipeline
(AD-2: the API builds a summary from tables and calls this helper, never the pipeline's stages).

Times: `t_ms` of an event is wall milliseconds since the session start. A heart-rate sample at workout time `t`
(seconds) sits at `offset_s + t` seconds on the session clock, where `offset_s` is workout start minus session start.
Paused spans are excluded from every figure."""
import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

HR_MIN, HR_MAX = 25, 250  # bpm; a reading outside this is impossible and counts as no time
MAX_STEP_S = 120.0  # a sample never covers more than this
LONE_STEP_S = 60.0
MIN_OVERLAP_SHARE = 0.5


def match(start: datetime, end: datetime, workouts: Sequence[Any]) -> Any | None:
    """The workout (anything with `start_utc` and `end_utc`) overlapping the session the most. The overlap must be at
    least half of the shorter of the two; with none that big there is no match."""
    span = (end - start).total_seconds()
    best, best_key = None, None
    for w in workouts:
        wlen = (w.end_utc - w.start_utc).total_seconds()
        overlap = (min(end, w.end_utc) - max(start, w.start_utc)).total_seconds()
        shorter = min(span, wlen)
        if overlap <= 0 or shorter <= 0 or overlap < MIN_OVERLAP_SHARE * shorter:
            continue
        key = (overlap, w.start_utc)
        if best_key is None or key > best_key:
            best, best_key = w, key
    return best


def pause_windows(events: Sequence[dict], end_ms: int) -> list[tuple[int, int]]:
    """Paused wall spans in ms. A pause with no resume lasts to the end; stray resumes and repeats are ignored."""
    out: list[tuple[int, int]] = []
    since: int | None = None
    for e in sorted(events, key=lambda e: e["t_ms"]):
        if e["kind"] == "pause" and since is None:
            since = min(e["t_ms"], end_ms)
        elif e["kind"] == "resume" and since is not None:
            out.append((since, max(since, min(e["t_ms"], end_ms))))
            since = None
    if since is not None:
        out.append((since, max(since, end_ms)))
    return [w for w in out if w[1] > w[0]]


def active_spans(t0: int, t1: int, pauses: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """[t0, t1) in ms with the paused windows cut out."""
    out, cur = [], t0
    for a, b in pauses:
        if b <= cur or a >= t1:
            continue
        if a > cur:
            out.append((cur, a))
        cur = max(cur, b)
    if cur < t1:
        out.append((cur, t1))
    return out


@dataclass
class Segment:
    move: int
    round: int
    t0: int
    t1: int
    rest: bool
    finished: bool  # closed by a tap or an automatic change, not by the runner ending the session


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


def segments(events: Sequence[dict], fmt: str, n_moves: int, end_ms: int) -> list[Segment]:
    """The timeline cut at every event that moves the runner on. An event's move and round name where the runner was
    just before it, so each one closes the segment it names. After the last move of a round (AMRAP, complex) comes
    a rest that the next event closes."""
    out: list[Segment] = []
    cur, rest = 0, False
    for e in sorted(events, key=lambda e: e["t_ms"]):
        kind = e["kind"]
        if kind not in ("next", "auto", "end"):
            continue
        t1 = min(max(cur, e["t_ms"]), max(cur, end_ms))  # nothing runs past the session's end
        out.append(Segment(e["move"], e["round"], cur, t1, rest, kind != "end"))
        cur = t1
        if kind == "end":
            break
        if fmt != "emom":
            rest = False if rest else e["move"] >= n_moves - 1
    return out


class Samples:
    """Heart-rate readings on the session clock. Each covers the time to the next one (capped), so the density of the
    export never changes a result."""

    def __init__(self, t: Sequence[float], avg: Sequence[float], offset_s: float):
        pairs = sorted(((offset_s + x, a) for x, a in zip(t, avg) if _num(x) and _num(a)), key=lambda p: p[0])
        self.starts = [p[0] for p in pairs]
        self.hr = [p[1] for p in pairs]
        n = len(pairs)
        gaps = [b - a for a, b in zip(self.starts, self.starts[1:]) if b > a]
        last = min(gaps[-1], MAX_STEP_S) if gaps else LONE_STEP_S
        self.ends = [s + min(self.starts[i + 1] - s if i + 1 < n else last, MAX_STEP_S) for i, s in enumerate(self.starts)]

    def __bool__(self) -> bool:
        return bool(self.starts)

    def slices(self, spans_ms: Sequence[tuple[int, int]]):
        """(hr, seconds) for each valid reading, clipped to the spans."""
        for a_ms, b_ms in spans_ms:
            a, b = a_ms / 1000, b_ms / 1000
            i = max(0, bisect_left(self.starts, a - MAX_STEP_S) - 1)
            while i < len(self.starts) and self.starts[i] < b:
                hr = self.hr[i]
                w = min(self.ends[i], b) - max(self.starts[i], a)
                if w > 0 and HR_MIN <= hr <= HR_MAX:
                    yield hr, w
                i += 1

    def mean(self, spans_ms: Sequence[tuple[int, int]]) -> tuple[float, float] | None:
        """(time-weighted mean bpm, seconds covered), or None with no reading in the spans."""
        total = secs = 0.0
        for hr, w in self.slices(spans_ms):
            total += hr * w
            secs += w
        return (total / secs, secs) if secs > 0 else None

    def zones(self, spans_ms: Sequence[tuple[int, int]], bounds: Sequence[float]) -> list[float] | None:
        out = [0.0] * (len(bounds) + 1)
        for hr, w in self.slices(spans_ms):
            out[sum(hr > b for b in bounds)] += w
        return out if any(out) else None


@dataclass
class RoundRow:
    round: int  # 1-based
    time_s: int
    moves: int
    avg_hr: float | None


@dataclass
class MoveRow:
    name: str
    avg_hr: float
    instances: int


@dataclass
class Computed:
    moves: list[MoveRow] = field(default_factory=list)
    rounds: list[RoundRow] = field(default_factory=list)
    avg_hr: float | None = None
    zone_seconds: list[float] | None = None


def _mean(parts: Sequence[tuple[float, float]]) -> float | None:
    secs = sum(w for _, w in parts)
    return sum(m * w for m, w in parts) / secs if secs > 0 else None


def compute(events: Sequence[dict], plan: dict, end_ms: int, samples: Samples | None,
            zone_bounds: Sequence[float] | None) -> Computed:
    """Per-round rows (always, from the taps), and heart-rate figures when there are `samples`. Only finished work
    segments count toward moves and rounds: the move the runner was still on when he ended is left out."""
    moves = plan["moves"]
    by_round_tap = plan.get("tap_per") == "round" and plan["format"] != "emom"  # one tap per round: no per-move taps
    pauses = pause_windows(events, end_ms)
    segs = [s for s in segments(events, plan["format"], len(moves), end_ms) if not s.rest and s.finished and s.move < len(moves)]
    out = Computed()
    by_name: dict[str, list[tuple[float, float]]] = {}
    by_round: dict[int, list[Segment]] = {}
    round_hr: dict[int, list[tuple[float, float]]] = {}
    for s in segs:
        by_round.setdefault(s.round, []).append(s)
        if samples:
            m = samples.mean(active_spans(s.t0, s.t1, pauses))
            if m:
                if not by_round_tap:
                    by_name.setdefault(moves[s.move]["name"], []).append(m)
                round_hr.setdefault(s.round, []).append(m)
    for name, parts in by_name.items():
        out.moves.append(MoveRow(name, round(_mean(parts) or 0, 1), len(parts)))
    for r in sorted(by_round):
        rs = by_round[r]
        time_s = sum(b - a for s in rs for a, b in active_spans(s.t0, s.t1, pauses)) / 1000
        hr = _mean(round_hr.get(r, []))
        out.rounds.append(RoundRow(r + 1, round(time_s), len(moves) if by_round_tap else len(rs), None if hr is None else round(hr, 1)))
    if samples:
        whole = active_spans(0, end_ms, pauses)
        m = samples.mean(whole)
        out.avg_hr = None if m is None else round(m[0], 1)
        if zone_bounds:
            out.zone_seconds = samples.zones(whole, zone_bounds)
    return out

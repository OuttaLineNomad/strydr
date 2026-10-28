"""Sleep stage samples -> one HAE-shaped `sleep_analysis` night per wake-up date. Pure: no I/O, no clock.

A sample is (stage, source, start_utc, end_utc) with naive UTC datetimes. Stages are the HealthKit
names without their prefix: InBed, AsleepUnspecified, AsleepCore, AsleepDeep, AsleepREM, Awake.
"""
from collections import defaultdict
from datetime import UTC, datetime, timedelta, tzinfo

Sample = tuple[str, str, datetime, datetime]

JOIN_GAP = timedelta(hours=2)
ASLEEP = ("AsleepCore", "AsleepDeep", "AsleepREM", "AsleepUnspecified")


def _seconds(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds()


def _union(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[list[datetime]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def sessions(samples: list[Sample]) -> list[list[Sample]]:
    """Group samples into sessions: a gap of 2 h or less to the session so far joins them."""
    out: list[list[Sample]] = []
    end: datetime | None = None
    for s in sorted(samples, key=lambda x: (x[2], x[3], x[0], x[1])):
        if out and end is not None and s[2] - end <= JOIN_GAP:
            out[-1].append(s)
            end = max(end, s[3])
        else:
            out.append([s])
            end = s[3]
    return out


def best_source(session: list[Sample]) -> str | None:
    """The single source with the most asleep time, or None when nobody has any. Ties go to the lowest name."""
    totals: dict[str, float] = defaultdict(float)
    for st, src, a, b in session:
        if st in ASLEEP:
            totals[src] += _seconds(a, b)
    if not totals:
        return None
    return min(totals, key=lambda s: (-totals[s], s))


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds") + "Z"


def build_extra(session: list[Sample]) -> dict | None:
    """HAE's `extra` for one session, or None when it holds no sleep."""
    src = best_source(session)
    if src is None:
        return None
    mine = [s for s in session if s[1] == src]
    by_stage: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for st, _, a, b in mine:
        by_stage[st].append((a, b))
    # overlapping samples of one stage from one source count once
    hours = {st: sum(_seconds(a, b) for a, b in _union(iv)) / 3600 for st, iv in by_stage.items()}
    hours = defaultdict(float, hours)
    modern = any(st in ("AsleepCore", "AsleepDeep", "AsleepREM") for st, *_ in mine)
    extra: dict = {}
    parts = [hours["AsleepCore"], hours["AsleepDeep"], hours["AsleepREM"], hours["AsleepUnspecified"]]
    extra["totalSleep"] = sum(parts)
    extra["asleep"] = hours["AsleepUnspecified"]
    if modern:
        extra["core"], extra["deep"], extra["rem"] = parts[0], parts[1], parts[2]
    extra["awake"] = hours["Awake"]
    bed = _union([(a, b) for st, _, a, b in session if st == "InBed"])
    extra["inBed"] = sum(_seconds(a, b) for a, b in bed) / 3600
    asleep = [(a, b) for st, _, a, b in mine if st in ASLEEP]
    extra["sleepStart"] = _iso(min(a for a, _ in asleep))
    extra["sleepEnd"] = _iso(max(b for _, b in asleep))
    if bed:
        extra["inBedStart"] = _iso(bed[0][0])
        extra["inBedEnd"] = _iso(bed[-1][1])
    return extra


def nights(samples: list[Sample], home_tz: tzinfo) -> list[tuple[str, dict]]:
    """(local_date, extra) per night, ordered by date. A session is dated by the local date of its end;
    when a date has several sessions the one with the most sleep wins."""
    best: dict[str, dict] = {}
    for sess in sessions(samples):
        extra = build_extra(sess)
        if extra is None:
            continue
        end = max(b for *_, b in sess)
        date = end.replace(tzinfo=UTC).astimezone(home_tz).strftime("%Y-%m-%d")
        if date not in best or extra["totalSleep"] > best[date]["totalSleep"]:
            best[date] = extra
    return sorted(best.items())

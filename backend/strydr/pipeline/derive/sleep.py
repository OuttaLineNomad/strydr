"""The night before a run: sleep and the next morning's recovery readings. Pure: no DB, clock or I/O.

HAE dates a night by the morning it ended (`sleepEnd`). The night before a run is the latest night that ended
before the run started and within `MAX_GAP_H` of it, so an afternoon nap or a missing night never stands in.
"Usual" is the median of the previous `NORM_NIGHTS` nights (from `MIN_NORM_NIGHTS` up); quality is a plain
read of duration against that usual and of time awake. Apple gives no sleep score, so neither does Strydr.
"""
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

MAX_GAP_H = 18.0
NORM_NIGHTS = 30
MIN_NORM_NIGHTS = 7
SHORT_H = 1.0  # this much under usual (or under 6 h without a usual) reads as a short night
RESTLESS_AWAKE_PCT = 15.0
LATE_WORN_START = (4, 11)  # a night starting in these home-local hours looks like a watch put on at dawn
LATE_WORN_UNDER_USUAL_H = 3.0  # and this much under the usual (or under this many hours without one)


def overlay(nights: list[tuple[str, dict]], corrections: dict[str, float]) -> list[tuple[str, dict]]:
    """Apply the runner's hours to `totalSleep` only; stages and awake stay as recorded. Marks each with `corrected`."""
    return [(d, {**x, "totalSleep": corrections[d], "corrected": True}) if d in corrections else (d, x) for d, x in nights]


def suspicious(extra: dict, usual_h: float | None, home_tz: ZoneInfo) -> bool:
    """Looks like a watch worn late: sleep began at dawn (04:00 to 11:00 home-local) and the total is at least 3 h
    under the usual, or under 3 h when there is no usual. A corrected night is not flagged."""
    total, start = extra.get("totalSleep"), _ts(extra.get("sleepStart"))
    if extra.get("corrected") or not total or start is None:
        return False
    hour = start.replace(tzinfo=ZoneInfo("UTC")).astimezone(home_tz).hour
    if not LATE_WORN_START[0] <= hour < LATE_WORN_START[1]:
        return False
    return total <= usual_h - LATE_WORN_UNDER_USUAL_H if usual_h is not None else total < LATE_WORN_UNDER_USUAL_H


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def night_before(nights: list[tuple[str, dict]], start_utc: datetime) -> tuple[str, dict] | None:
    """`nights` are (local_date, extra) sorted by date. Returns the night that ended last before start_utc."""
    best = None
    for d, x in nights:
        end = _ts(x.get("sleepEnd"))
        if end is None or not x.get("totalSleep"):
            continue
        if end <= start_utc and start_utc - end <= timedelta(hours=MAX_GAP_H):
            best = (d, x)
    return best


def _usual(nights: list[tuple[str, dict]], before: str) -> float | None:
    prior = [x["totalSleep"] for d, x in nights if d < before and x.get("totalSleep")][-NORM_NIGHTS:]
    return median(prior) if len(prior) >= MIN_NORM_NIGHTS else None


def _baseline(daily: dict[str, float], day: str) -> float | None:
    lo = (date.fromisoformat(day) - timedelta(days=NORM_NIGHTS)).isoformat()
    vals = [v for d, v in daily.items() if lo <= d < day]
    return median(vals) if len(vals) >= MIN_NORM_NIGHTS else None


def quality(total_h: float, awake_h: float, usual_h: float | None) -> str:
    """short | restless | good | fair: a closed word, also an AI term."""
    awake_pct = awake_h / (total_h + awake_h) * 100 if total_h + awake_h > 0 else 0.0
    if (usual_h is not None and total_h <= usual_h - SHORT_H) or total_h < 6.0:
        return "short"
    if awake_pct >= RESTLESS_AWAKE_PCT:
        return "restless"
    if total_h >= 7.0 or (usual_h is not None and total_h >= usual_h - 0.25):
        return "good"
    return "fair"


def before_run(nights: list[tuple[str, dict]], start_utc: datetime, utc_offset_s: int,
               rhr: dict[str, float], hrv: dict[str, float], home_tz: ZoneInfo | None = None) -> dict | None:
    """The sleep and morning readings for a run, or None when no night qualifies."""
    hit = night_before(nights, start_utc)
    if hit is None:
        return None
    day, x = hit
    total, awake = x["totalSleep"], x.get("awake") or 0.0
    deep, rem, core = x.get("deep"), x.get("rem"), x.get("core")
    usual = _usual(nights, day)
    off = timedelta(seconds=utc_offset_s)
    s, e = _ts(x.get("sleepStart")), _ts(x.get("sleepEnd"))
    fixed = bool(x.get("corrected"))  # stages are the short recording, so ratios against the runner's hours would mislead
    out = {
        "night_of": day,
        "total_h": round(total, 2), "deep_h": _r(deep), "rem_h": _r(rem), "core_h": _r(core), "awake_h": round(awake, 2),
        "bedtime": (s + off).strftime("%H:%M") if s else None, "wake": (e + off).strftime("%H:%M") if e else None,
        "hours_before_run": round((start_utc - e).total_seconds() / 3600, 1) if e else None,
        "efficiency_pct": round(total / (total + awake) * 100) if total + awake > 0 and not fixed else None,
        "deep_rem_pct": round(((deep or 0) + (rem or 0)) / total * 100) if total and deep is not None and rem is not None and not fixed else None,
        "usual_h": round(usual, 2) if usual is not None else None,
        "vs_usual_h": round(total - usual, 2) if usual is not None else None,
        "quality": quality(total, awake, usual),
        "corrected": fixed,
        "suspicious": suspicious(x, usual, home_tz) if home_tz is not None else False,
        "rhr_bpm": rhr.get(day), "rhr_usual_bpm": _r(_baseline(rhr, day), 1),
        "hrv_ms": _r(hrv.get(day), 1), "hrv_usual_ms": _r(_baseline(hrv, day), 1),
    }
    return out


def _r(v: float | None, n: int = 2) -> float | None:
    return round(v, n) if v is not None else None

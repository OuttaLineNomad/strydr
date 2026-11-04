"""Health Auto Export JSON -> canonical models (AD-4). The only code that knows the HAE format.

Bump ADAPTER_VERSION whenever the parsing output changes (AD-1: triggers a reparse).
"""
import math
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import BinaryIO

import ijson
from ijson.common import ObjectBuilder

from strydr.sources.canonical import DailyMetric, SampleSeries, Workout, active_seconds, fallback_workout_id
from strydr.sources.hae.units import convert, passthrough

ADAPTER_VERSION = 3  # 2: active time (pauses removed), the watch's own speed, elevation and splits; 3: step_count series

HR_MIN, HR_MAX = 25, 250  # bpm; outside this range a sample is impossible
MAX_SPEED_MPS = 12.0
_TS = "%Y-%m-%d %H:%M:%S %z"
_TYPES = {"running": "run", "walking": "walk", "hiking": "hike"}
_TYPE_CODES = {37: "run", 52: "walk", 24: "hike"}
_HR_UNITS = {"count/min", "bpm"}
_ITEMS = {"data.metrics.item": "metric", "data.workouts.item": "workout"}


class AdapterError(Exception):
    """Raised for payloads that are structurally not an HAE export. Messages never contain payload values."""


def parse(stream: BinaryIO) -> Iterator[Workout | DailyMetric]:
    """Stream-parse an export, holding one workout or metric in memory at a time."""
    builder: ObjectBuilder | None = None
    kind = ""
    seen_data = False
    try:
        for prefix, event, value in ijson.parse(stream, use_float=True):
            if builder is None:
                if prefix == "data" and event == "start_map":
                    seen_data = True
                if prefix in _ITEMS and event == "start_map":
                    builder, kind = ObjectBuilder(), _ITEMS[prefix]
                    builder.event(event, value)
                continue
            builder.event(event, value)
            if prefix in _ITEMS and event == "end_map":
                item, builder = builder.value, None
                if kind == "workout":
                    w = convert_workout(item)
                    if w is not None:
                        yield w
                else:
                    yield from convert_metric(item)
    except ijson.JSONError as e:
        raise AdapterError("malformed JSON") from e
    if not seen_data:
        raise AdapterError("not an HAE export: missing top-level 'data'")


# --- timestamps -------------------------------------------------------------

def _ts(s: str) -> tuple[datetime, int, str]:
    dt = datetime.strptime(s, _TS)
    off = int(dt.utcoffset().total_seconds())
    return dt.astimezone(UTC).replace(tzinfo=None), off, dt.strftime("%Y-%m-%d")


def _utc(s: str) -> datetime:
    return _ts(s)[0]


# --- scalar helpers (always read `units`) ------------------------------------

def _qty(obj, key: str, want: str, flags: dict, units_alias: dict | None = None) -> float | None:
    """Convert obj[key] = {qty, units} to the canonical unit `want`; flag unknown units."""
    o = obj.get(key)
    if not isinstance(o, dict) or not isinstance(o.get("qty"), (int, float)):
        return None
    units = o.get("units")
    if units_alias and units in units_alias:
        units = units_alias[units]
    r = convert(o["qty"], units)
    if r is None or r[1] != want:
        flags[f"unit_{key}"] = flags.get(f"unit_{key}", 0) + 1
        return None
    return float(r[0])


def _plain(obj, key: str, units: set[str], flags: dict) -> float | None:
    o = obj.get(key)
    if not isinstance(o, dict) or not isinstance(o.get("qty"), (int, float)):
        return None
    if o.get("units") not in units:
        flags[f"unit_{key}"] = flags.get(f"unit_{key}", 0) + 1
        return None
    return float(o["qty"])


# --- workouts ---------------------------------------------------------------

def _workout_type(w: dict) -> str | None:
    acts = w.get("activities") or [{}]
    a = acts[0] if isinstance(acts[0], dict) else {}
    if a.get("activityType") in _TYPES:
        return _TYPES[a["activityType"]]
    if a.get("activityTypeCode") in _TYPE_CODES:
        return _TYPE_CODES[a["activityTypeCode"]]
    name = str(w.get("name", "")).lower()
    for needle, t in (("run", "run"), ("walk", "walk"), ("hik", "hike")):
        if needle in name:
            return t
    return None


def convert_workout(w: dict) -> Workout | None:
    wtype = _workout_type(w)
    if wtype is None or "start" not in w or "end" not in w:
        return None  # other workout types stay in raw only (AD-4)
    start_utc, offset, local_date = _ts(w["start"])
    end_utc = _utc(w["end"])
    wid = w.get("id") or (w.get("activities") or [{}])[0].get("id")
    if not wid:
        wid = fallback_workout_id(wtype, start_utc)
    flags: dict[str, int] = {}
    indoor = bool(w["isIndoor"]) if "isIndoor" in w else str(w.get("location", "")).lower() == "indoor"

    hr_obj = w.get("heartRate") if isinstance(w.get("heartRate"), dict) else {}
    avg_hr = _plain(w, "avgHeartRate", _HR_UNITS, flags) or _plain(hr_obj, "avg", _HR_UNITS, flags)
    max_hr = _plain(w, "maxHeartRate", _HR_UNITS, flags) or _plain(hr_obj, "max", _HR_UNITS, flags)
    effort = _plain(w, "effortScore", {"appleEffortScore"}, flags)
    estimated = False
    if effort is None:
        effort = _plain(w, "estimatedEffortScore", {"appleEffortScore"}, flags)
        estimated = effort is not None

    # HAE labels avgSpeed/maxSpeed "mi" although the values are mi/hr.
    mislabel = {"mi": "mi/hr"}
    speed = _qty(w, "speed", "m/s", flags)
    out = Workout(
        workout_id=str(wid), type=wtype, is_indoor=indoor,
        start_utc=start_utc, end_utc=end_utc, utc_offset_s=offset, local_date=local_date,
        duration_s=float(w["duration"]) if isinstance(w.get("duration"), (int, float)) else None,
        distance_m=_qty(w, "distance", "m", flags),
        avg_speed_mps=_active_speed(w, flags) or _qty(w, "avgSpeed", "m/s", flags, mislabel) or speed,
        max_speed_mps=_qty(w, "maxSpeed", "m/s", flags, mislabel),
        avg_hr=avg_hr, max_hr=max_hr,
        avg_cadence=_plain(w, "stepCadence", {"count/min"}, flags),
        energy_kcal=_plain(w, "activeEnergyBurned", {"kcal"}, flags),
        temperature_c=_qty(w, "temperature", "degC", flags),
        humidity_pct=_plain(w, "humidity", {"%"}, flags),
        effort_score=effort, effort_estimated=estimated if effort is not None else None,
    )

    pauses = _pauses(w.get("events"), start_utc)
    hr = _hr_series(w.get("heartRateData"), start_utc, flags)
    if hr:
        hr.columns["at"] = [active_seconds(t, pauses) for t in hr.columns["t"]]
        out.series["heart_rate"] = hr
    route = _route_series(w.get("route"), start_utc, flags)
    if route:
        route.columns["at"] = [active_seconds(t, pauses) for t in route.columns["t"]]
        out.series["route"] = route
    steps = _step_series(w.get("stepCount"), start_utc, end_utc, flags)
    if steps:
        out.series["step_count"] = steps
    splits = _splits_series(w.get("splits"), flags)
    if splits:
        out.series["splits"] = splits
    # The watch's own ascent is what Apple shows; the GPS altitude estimate is the fallback.
    gain = _qty(w, "elevationUp", "m", flags)
    out.elevation_gain_m = gain if gain is not None else (_elevation_gain(route.columns["alt"]) if route else None)
    if out.avg_speed_mps is None and out.distance_m and out.duration_s:
        out.avg_speed_mps = out.distance_m / out.duration_s
    out.quality_flags = flags
    return out


def _active_speed(w: dict, flags: dict) -> float | None:
    """Speed over active (moving) time, as Apple computes average pace. HAE's avgSpeed uses elapsed time."""
    acts = w.get("activities")
    if isinstance(acts, list) and acts and isinstance(acts[0], dict):
        v = _qty(acts[0].get("metrics") or {}, "speed", "m/s", flags)
        if v:
            return v
    d, t = w.get("distance"), w.get("duration")
    if isinstance(t, (int, float)) and t > 0 and isinstance(d, dict):
        metres = _qty(w, "distance", "m", flags)
        return metres / t if metres else None
    return None


def _pauses(events, start: datetime) -> list[tuple[float, float]]:
    """Paused intervals in seconds since start, from pause/resume events (manual and automatic)."""
    if not isinstance(events, list):
        return []
    out: list[tuple[float, float]] = []
    began: float | None = None
    for e in events:
        try:
            kind = str(e.get("type", "")).lower()
            t = (_utc(e["start"]) - start).total_seconds()
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if "pause" in kind and began is None:
            began = t
        elif "resume" in kind and began is not None:
            if t > began:
                out.append((began, t))
            began = None
    return sorted(out)


def _splits_series(groups, flags: dict) -> SampleSeries | None:
    """The watch's own fixed-distance splits (per km and per mile), active time and average HR per split."""
    if not isinstance(groups, list):
        return None
    cols: dict[str, list] = {"t": [], "unit": [], "index": [], "distance_m": [], "duration_s": [], "avg_hr": []}
    for g in groups:
        if not isinstance(g, dict):
            continue
        unit = (g.get("targetDistance") or {}).get("units")
        if unit not in ("km", "mi") or not isinstance(g.get("items"), list):
            continue
        elapsed = 0.0  # active seconds at each split's start
        for i, it in enumerate(g["items"]):
            try:
                m = it.get("metrics") or {}
                dist = _qty(m, "distance", "m", flags)
                dur = float(it["activeDuration"])
                t = elapsed
            except (AttributeError, KeyError, TypeError, ValueError):
                flags["splits_dropped"] = flags.get("splits_dropped", 0) + 1
                continue
            if not dist or dur <= 0:
                continue
            elapsed += dur
            cols["t"].append(t)
            cols["unit"].append(unit)
            cols["index"].append(i)
            cols["distance_m"].append(dist)
            cols["duration_s"].append(dur)
            cols["avg_hr"].append(_plain(m, "heartRateAverage", _HR_UNITS, flags))
    return SampleSeries("splits", cols) if cols["t"] else None


def _hr_series(items, start: datetime, flags: dict) -> SampleSeries | None:
    if not isinstance(items, list):
        return None
    cols: dict[str, list] = {"t": [], "min": [], "avg": [], "max": []}
    for s in items:
        try:
            vals = [s["Min"], s["Avg"], s["Max"]]
            t = (_utc(s["date"]) - start).total_seconds()
            ok = s.get("units", "count/min") in _HR_UNITS and all(HR_MIN <= v <= HR_MAX for v in vals)
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            flags["hr_samples_dropped"] = flags.get("hr_samples_dropped", 0) + 1
            continue
        cols["t"].append(t)
        for k, v in zip(("min", "avg", "max"), vals):
            cols[k].append(float(v))
    return SampleSeries("heart_rate", cols) if cols["t"] else None


STEP_DT_CAP = 60.0  # s; a gap (a paused watch) must not stretch one sample's interval


def _step_series(items, start: datetime, end: datetime, flags: dict) -> SampleSeries | None:
    """HAE's stepCount samples as intervals: dt is the gap to the next sample (the last gets the median gap)."""
    if not isinstance(items, list):
        return None
    span = (end - start).total_seconds()
    rows: list[tuple[float, float]] = []
    for s in items:
        try:
            qty = s["qty"]
            t = (_utc(s["date"]) - start).total_seconds()
            ok = (isinstance(qty, (int, float)) and not isinstance(qty, bool) and math.isfinite(qty) and qty >= 0
                  and s.get("units", "count") == "count" and 0 <= t <= span)
        except (KeyError, TypeError, ValueError, AttributeError):
            ok = False
        if not ok:
            flags["step_samples_dropped"] = flags.get("step_samples_dropped", 0) + 1
            continue
        rows.append((t, float(qty)))
    if not rows:
        return None
    merged: dict[float, float] = {}
    for t, qty in rows:  # samples at the same instant are one sample
        merged[t] = merged.get(t, 0.0) + qty
    rows = sorted(merged.items())
    gaps = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    last = sorted(gaps)[len(gaps) // 2] if gaps else STEP_DT_CAP
    dts = [min(g, STEP_DT_CAP) for g in gaps] + [min(last, STEP_DT_CAP)]
    return SampleSeries("step_count", {"t": [r[0] for r in rows], "dt": dts, "steps": [r[1] for r in rows]})


def _route_series(items, start: datetime, flags: dict) -> SampleSeries | None:
    if not isinstance(items, list):
        return None
    cols: dict[str, list] = {"t": [], "lat": [], "lon": [], "alt": [], "speed": []}
    for p in items:
        try:
            t = (_utc(p["timestamp"]) - start).total_seconds()
            lat, lon = float(p["latitude"]), float(p["longitude"])
            alt = p.get("altitude")
            spd = p.get("speed")
        except (KeyError, TypeError, ValueError):
            flags["route_points_dropped"] = flags.get("route_points_dropped", 0) + 1
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (isinstance(spd, (int, float)) and spd > MAX_SPEED_MPS):
            flags["route_points_dropped"] = flags.get("route_points_dropped", 0) + 1
            continue
        cols["t"].append(t)
        cols["lat"].append(lat)
        cols["lon"].append(lon)
        cols["alt"].append(float(alt) if isinstance(alt, (int, float)) else None)
        cols["speed"].append(float(spd) if isinstance(spd, (int, float)) and spd >= 0 else None)
    return SampleSeries("route", cols) if cols["t"] else None


def _elevation_gain(alts: list, threshold: float = 3.0) -> float | None:
    """Cumulative ascent with hysteresis, so GPS altitude noise is not counted as climbing."""
    vals = [a for a in alts if a is not None]
    if not vals:
        return None
    gain, ref = 0.0, vals[0]
    for a in vals[1:]:
        if a - ref >= threshold:
            gain += a - ref
            ref = a
        elif a < ref:
            ref = a
    return gain


# --- daily metrics ----------------------------------------------------------

def convert_metric(m: dict) -> Iterator[DailyMetric]:
    name, units, data = m.get("name"), m.get("units", ""), m.get("data")
    if not isinstance(name, str) or not isinstance(data, list):
        return
    for p in data:
        try:
            local_date = p["date"][:10]
            datetime.strptime(local_date, "%Y-%m-%d")
            if name == "sleep_analysis":
                yield _sleep(p, local_date)
            elif "Avg" in p:
                vals = {k.lower(): float(p[k]) for k in ("Min", "Avg", "Max") if isinstance(p.get(k), (int, float))}
                yield DailyMetric(name, local_date, units, vals.get("avg"), vals, len(vals))
            elif isinstance(p.get("qty"), (int, float)):
                v, u = passthrough(float(p["qty"]), units)
                yield DailyMetric(name, local_date, u, v)
        except (KeyError, TypeError, ValueError):
            continue


def _sleep(p: dict, local_date: str) -> DailyMetric:
    extra: dict = {}
    for k in ("totalSleep", "asleep", "core", "deep", "rem", "awake", "inBed"):
        if isinstance(p.get(k), (int, float)):
            extra[k] = float(p[k])
    for k in ("sleepStart", "sleepEnd", "inBedStart", "inBedEnd"):
        if isinstance(p.get(k), str):
            try:
                extra[k] = _utc(p[k]).isoformat(timespec="seconds") + "Z"
            except ValueError:
                pass
    return DailyMetric("sleep_analysis", local_date, "hr", extra.get("totalSleep"), extra, len(extra))

"""Apple Health `export.xml` -> canonical models (AD-4). The only code that knows the Apple export format.

Streams with iterparse so memory stays bounded. Bump ADAPTER_VERSION whenever the parsing output changes
(AD-1: triggers a reparse). Error messages never contain values, names, dates or source names.
"""
import zipfile
from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, tzinfo
from typing import BinaryIO
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from strydr.sources.apple import sleep
from strydr.sources.canonical import DailyMetric, SampleSeries, Workout, active_seconds, fallback_workout_id
from strydr.sources.hae.units import convert

ADAPTER_VERSION = 2

HR_MIN, HR_MAX = 25, 250  # bpm; outside this range a sample is impossible (same bounds as the HAE adapter)
MAX_SPEED_MPS = 12.0

_TS = "%Y-%m-%d %H:%M:%S %z"
_TYPES = {"Running": "run", "Walking": "walk", "Hiking": "hike"}
_Q = "HKQuantityTypeIdentifier"
_HR = _Q + "HeartRate"
_SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
_SLEEP_PREFIX = "HKCategoryValueSleepAnalysis"
_SLEEP_STAGES = {"InBed", "Asleep", "AsleepUnspecified", "AsleepCore", "AsleepDeep", "AsleepREM", "Awake"}
# record type -> (HAE metric name, HAE units, accepted source units). Temperature converts via units.convert.
_METRICS = {
    _Q + "RestingHeartRate": ("resting_heart_rate", "count/min", {"count/min"}),
    _Q + "HeartRateVariabilitySDNN": ("heart_rate_variability", "ms", {"ms"}),
    _Q + "RespiratoryRate": ("respiratory_rate", "count/min", {"count/min"}),
    _Q + "VO2Max": ("vo2_max", "ml/(kg·min)", {"mL/min·kg", "mL/min*kg", "mL/(kg·min)", "ml/(kg·min)"}),
    _Q + "AppleSleepingWristTemperature": ("apple_sleeping_wrist_temperature", "degC", None),
}
_DURATION_S = {"min": 60.0, "s": 1.0, "sec": 1.0, "hr": 3600.0, "h": 3600.0}
_HR_UNITS = {"count/min", "bpm"}
_ENERGY_KCAL = {"Cal": 1.0, "kcal": 1.0, "kJ": 0.2390057361376673}


class AdapterError(Exception):
    """Raised for input that is structurally not an Apple Health export. Messages never contain input values."""


def parse(stream: BinaryIO, home_tz: tzinfo,
          open_route: Callable[[str], BinaryIO | None] | None = None) -> Iterator[Workout | DailyMetric]:
    """Stream-parse an export. Workouts are yielded after the stream ends (their heart rate records precede
    them in the file), then daily metrics and sleep.

    `open_route(path)` resolves a workout's `FileReference` path (such as `/workout-routes/route_....gpx`) to a
    binary stream, or None. Without it, or when the file is missing or unreadable, a workout has no route and
    carries `quality_flags["route_missing"]`.

    Malformed XML can surface late: output seen before an AdapterError is partial and the caller must not commit it.
    """
    sums: dict[tuple[str, str], list] = {}  # (metric, local_date) -> [units, total, count]
    sleep_samples: list[sleep.Sample] = []
    seen: set[tuple] = set()  # identical records (a nested copy of a top-level one) count once
    hr = _HeartRates()
    pending: list[tuple[Workout, str | None, list[tuple[float, float]], str | None]] = []
    depth = 0
    root = None
    in_workout = in_other = False  # inside a top-level Workout / Correlation
    try:
        for event, el in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                if root is None:
                    if el.tag != "HealthData":
                        raise AdapterError("not an Apple Health export: unexpected root element")
                    root = el
                elif depth == 1:
                    in_workout, in_other = el.tag == "Workout", el.tag == "Correlation"
                depth += 1
                continue
            depth -= 1
            if el.tag == "Record" and not in_other:
                if el.get("type") == _HR:
                    hr.add(el, nested=depth > 1)
                else:
                    _record(el, home_tz, sums, sleep_samples, seen)
            if el.tag == "Workout" and depth == 1:
                w = _workout(el)
                in_workout = False
                if w is not None:
                    pending.append((w, el.get("sourceName"), _pauses(el, w.start_utc), _route_path(el)))
                root.clear()
            elif depth == 1:
                in_other = False
                root.clear()  # drop handled top-level children; nested records wait for their workout's end
            elif depth > 1 and not in_workout:
                el.clear()
    except ET.ParseError as e:
        raise AdapterError("malformed XML") from e

    hr.finish()
    for w, source, pauses, route_path in pending:
        series = hr.series(w, source, pauses)
        if series:
            w.series["heart_rate"] = series
        if route_path is not None:
            route = _route(open_route, route_path, w.start_utc, w.end_utc, pauses, w.quality_flags)
            if route:
                w.series["route"] = route
        yield w
    pending.clear()

    for (metric, date), (units, total, n) in sorted(sums.items()):
        yield DailyMetric(metric, date, units, total / n)
    for date, extra in sleep.nights(sleep_samples, home_tz):
        yield DailyMetric("sleep_analysis", date, "hr", extra["totalSleep"], extra, len(extra))


# --- timestamps -------------------------------------------------------------

def _ts(s: str) -> tuple[datetime, int, str]:
    """(naive UTC, offset seconds, date text in the string's own offset)."""
    dt = datetime.strptime(s, _TS)
    return dt.astimezone(UTC).replace(tzinfo=None), int(dt.utcoffset().total_seconds()), dt.strftime("%Y-%m-%d")


def _local_date(utc: datetime, tz: tzinfo) -> str:
    return utc.replace(tzinfo=UTC).astimezone(tz).strftime("%Y-%m-%d")


# --- records: daily metrics and sleep ----------------------------------------

def _record(el, home_tz: tzinfo, sums: dict, sleep_samples: list, seen: set) -> None:
    rtype = el.get("type")
    metric = _METRICS.get(rtype)
    if metric is None and rtype != _SLEEP:
        return
    key = (rtype, el.get("sourceName"), el.get("startDate"), el.get("endDate"), el.get("value"))
    if key in seen:
        return
    seen.add(key)
    try:
        start, end = _ts(el.get("startDate"))[0], _ts(el.get("endDate"))[0]
        if rtype == _SLEEP:
            stage = (el.get("value") or "").removeprefix(_SLEEP_PREFIX)
            if stage in _SLEEP_STAGES and end > start:
                sleep_samples.append(("AsleepUnspecified" if stage == "Asleep" else stage,
                                      el.get("sourceName") or "", start, end))
            return
        name, units, accepted = metric
        value = float(el.get("value"))
    except (TypeError, ValueError):
        return
    if accepted is None:
        r = convert(value, el.get("unit") or "")
        if r is None or r[1] != units:
            return
        value = r[0]
    elif el.get("unit") not in accepted:
        return
    acc = sums.setdefault((name, _local_date(end, home_tz)), [units, 0.0, 0])
    acc[1] += value
    acc[2] += 1


# --- workouts ---------------------------------------------------------------

def _flag(flags: dict, key: str) -> None:
    flags[f"unit_{key}"] = flags.get(f"unit_{key}", 0) + 1


def _split(text: str | None) -> tuple[float, str] | None:
    """'41.2 degF' -> (41.2, 'degF')."""
    try:
        num, _, unit = (text or "").strip().partition(" ")
        return float(num), unit
    except ValueError:
        return None


def _length_m(value: float, unit: str) -> float | None:
    if unit == "cm":
        return value / 100
    r = convert(value, unit)
    return r[0] if r and r[1] == "m" else None


def _workout(el) -> Workout | None:
    wtype = _TYPES.get((el.get("workoutActivityType") or "").removeprefix("HKWorkoutActivityType"))
    if wtype is None:
        return None  # other workout types stay in raw only (AD-4)
    try:
        start_utc, str_offset, str_date = _ts(el.get("startDate"))
        end_utc = _ts(el.get("endDate"))[0]
    except (TypeError, ValueError):
        return None
    meta = {m.get("key"): m.get("value") for m in el.findall("MetadataEntry")}
    offset, local_date = str_offset, str_date
    try:
        local = start_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(meta["HKTimeZone"]))
        offset, local_date = int(local.utcoffset().total_seconds()), local.strftime("%Y-%m-%d")
    except (KeyError, TypeError, ValueError, OSError):  # missing, empty or unknown zone name
        pass
    stats = {}
    for s in el.findall("WorkoutStatistics"):
        stats.setdefault((s.get("type") or "").removeprefix(_Q), s)

    flags: dict[str, int] = {}
    duration = None
    try:
        duration = float(el.get("duration")) * _DURATION_S[el.get("durationUnit")]
    except KeyError:  # unknown or missing durationUnit
        _flag(flags, "duration")
    except (TypeError, ValueError):
        pass

    distance = None
    if (s := stats.get("DistanceWalkingRunning")) is not None and s.get("sum") is not None:
        try:
            distance = _length_m(float(s.get("sum")), s.get("unit") or "")
        except ValueError:
            pass
        if distance is None:
            _flag(flags, "distance")
    energy = None
    if (s := stats.get("ActiveEnergyBurned")) is not None and s.get("sum") is not None:
        try:
            energy = float(s.get("sum")) * _ENERGY_KCAL[s.get("unit")]
        except (KeyError, ValueError):
            _flag(flags, "activeEnergyBurned")
    avg_hr = max_hr = None
    if (s := stats.get("HeartRate")) is not None:
        if s.get("unit") in _HR_UNITS:
            try:
                avg_hr = float(s.get("average")) if s.get("average") is not None else None
                max_hr = float(s.get("maximum")) if s.get("maximum") is not None else None
            except ValueError:
                pass
        else:
            _flag(flags, "avgHeartRate")
            _flag(flags, "maxHeartRate")

    temperature = humidity = gain = None
    if "HKWeatherTemperature" in meta:
        v = _split(meta["HKWeatherTemperature"])
        r = convert(*v) if v else None
        if r and r[1] == "degC":
            temperature = r[0]
        else:
            _flag(flags, "temperature")
    if "HKWeatherHumidity" in meta:
        v = _split(meta["HKWeatherHumidity"])
        if v and v[1] == "%":
            humidity = v[0] / 100  # Apple stores percent x 100
        else:
            _flag(flags, "humidity")
    if "HKElevationAscended" in meta:
        v = _split(meta["HKElevationAscended"])
        gain = _length_m(*v) if v else None
        if gain is None:
            _flag(flags, "elevationUp")

    return Workout(
        workout_id=fallback_workout_id(wtype, start_utc), type=wtype, is_indoor=meta.get("HKIndoorWorkout") == "1",
        start_utc=start_utc, end_utc=end_utc, utc_offset_s=offset, local_date=local_date,
        duration_s=duration, distance_m=distance,
        avg_speed_mps=distance / duration if distance is not None and duration else None,
        avg_hr=avg_hr, max_hr=max_hr, elevation_gain_m=gain, energy_kcal=energy,
        temperature_c=temperature, humidity_pct=humidity, quality_flags=flags,
    )


# --- heart rate -------------------------------------------------------------

def _epoch(text: str) -> float:
    """'2026-03-03 07:30:23 -0500' -> UTC epoch seconds. Faster than strptime; ValueError when malformed."""
    if len(text) != 25 or text[19] != " ":
        raise ValueError("timestamp")
    off = (int(text[21:23]) * 3600 + int(text[23:25]) * 60) * (-1 if text[20] == "-" else 1)
    return datetime.fromisoformat(text[:19]).replace(tzinfo=UTC).timestamp() - off


class _HeartRates:
    """Every HeartRate record of the export, kept compactly (midpoint epoch, value, source index) until the
    workouts, which come later in the file, can claim theirs."""

    def __init__(self) -> None:
        self.mid, self.val, self.src = array("d"), array("d"), array("H")
        self.nested: list[tuple[float, float, int]] = []  # records inside workouts: few, and out of file order
        self._sources: dict[str, int] = {}
        self._sorted = True

    def add(self, el, nested: bool) -> None:
        if el.get("unit") not in _HR_UNITS:
            return
        try:
            mid = (_epoch(el.get("startDate")) + _epoch(el.get("endDate"))) / 2
            value = float(el.get("value"))
        except (TypeError, ValueError):
            return
        name = el.get("sourceName") or ""
        src = self._sources.get(name)
        if src is None:  # new names past the array's range share the last index
            src = self._sources[name] = min(len(self._sources), 65535)
        if nested:
            self.nested.append((mid, value, src))
            return
        if self.mid and mid < self.mid[-1]:
            self._sorted = False
        self.mid.append(mid)
        self.val.append(value)
        self.src.append(src)

    def finish(self) -> None:
        if self._sorted:
            return
        import numpy as np  # only when the export is not chronological, which real ones are
        order = np.argsort(np.frombuffer(self.mid, dtype="d"), kind="stable")
        for name, typecode in (("mid", "d"), ("val", "d"), ("src", "H")):
            col = getattr(self, name)
            setattr(self, name, array(typecode, np.frombuffer(col, dtype=typecode)[order].tobytes()))

    def series(self, w: Workout, source: str | None, pauses: list[tuple[float, float]]) -> SampleSeries | None:
        start = w.start_utc.replace(tzinfo=UTC).timestamp()
        end = w.end_utc.replace(tzinfo=UTC).timestamp()
        lo, hi = bisect_left(self.mid, start), bisect_right(self.mid, end)
        found = {(self.mid[i], self.val[i], self.src[i]) for i in range(lo, hi)}
        found.update(r for r in self.nested if start <= r[0] <= end)  # a set: identical records count once
        valid = {r for r in found if HR_MIN <= r[1] <= HR_MAX}  # filter first, then pick the source
        own = self._sources.get(source or "")
        if own is not None and any(r[2] == own for r in valid):
            valid = {r for r in valid if r[2] == own}
            found = {r for r in found if r[2] == own}
        if dropped := len(found) - len(valid):
            w.quality_flags["hr_samples_dropped"] = w.quality_flags.get("hr_samples_dropped", 0) + dropped
        cols: dict[str, list] = {"t": [], "min": [], "avg": [], "max": [], "at": []}
        for mid, value, _ in sorted(valid):
            t = mid - start
            cols["t"].append(t)
            for k in ("min", "avg", "max"):
                cols[k].append(float(value))
            cols["at"].append(active_seconds(t, pauses))
        return SampleSeries("heart_rate", cols) if cols["t"] else None


# --- pauses and route --------------------------------------------------------

def _pauses(el, start: datetime) -> list[tuple[float, float]]:
    """Paused intervals in seconds since start, paired as the HAE adapter does. An unpaired pause is ignored."""
    events: list[tuple[float, str]] = []
    for e in el.findall("WorkoutEvent"):
        kind = (e.get("type") or "").lower()
        if "pause" not in kind and "resume" not in kind:
            continue
        try:
            events.append(((_ts(e.get("date"))[0] - start).total_seconds(), kind))
        except (TypeError, ValueError):
            continue
    out: list[tuple[float, float]] = []
    began: float | None = None
    for t, kind in sorted(events, key=lambda e: e[0]):  # by date, not file order
        if "pause" in kind and began is None:
            began = t
        elif "resume" in kind and began is not None:
            if t > began:
                out.append((began, t))
            began = None
    return sorted(out)


def _route_path(el) -> str | None:
    ref = el.find("WorkoutRoute/FileReference")
    return ref.get("path") if ref is not None and ref.get("path") else None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _gpx_time(text: str | None) -> datetime:
    dt = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _route(open_route, path: str, start: datetime, end: datetime, pauses: list[tuple[float, float]],
           flags: dict) -> SampleSeries | None:
    """Stream the workout's GPX into the route series. An unreadable file means no route and a flag."""
    cols: dict[str, list] = {"t": [], "lat": [], "lon": [], "alt": [], "speed": [], "at": []}
    dropped = 0
    f = None
    try:
        f = open_route(path) if open_route is not None else None
        if f is None:
            raise OSError("no route file")
        for _, el in ET.iterparse(f, events=("end",)):
            if _local(el.tag) != "trkpt":
                continue
            ele = time = spd = None
            for c in el:
                name = _local(c.tag)
                if name == "ele":
                    ele = c.text
                elif name == "time":
                    time = c.text
                elif name == "extensions":
                    spd = next((x.text for x in c if _local(x.tag) == "speed"), None)
            lat_s, lon_s = el.get("lat"), el.get("lon")
            el.clear()
            try:
                lat, lon = float(lat_s), float(lon_s)
                moment = _gpx_time(time)
            except (TypeError, ValueError):
                dropped += 1
                continue
            try:
                speed = float(spd) if spd is not None else None
            except ValueError:
                speed = None
            try:
                alt = float(ele) if ele is not None else None
            except ValueError:
                alt = None
            if (not (-90 <= lat <= 90 and -180 <= lon <= 180) or (speed is not None and speed > MAX_SPEED_MPS)
                    or not start <= moment <= end):
                dropped += 1
                continue
            t = (moment - start).total_seconds()
            cols["t"].append(t)
            cols["lat"].append(lat)
            cols["lon"].append(lon)
            cols["alt"].append(alt)
            cols["speed"].append(speed if speed is not None and speed >= 0 else None)
            cols["at"].append(active_seconds(t, pauses))
    except (OSError, ET.ParseError, UnicodeError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        flags["route_missing"] = 1
        return None
    finally:
        if f is not None:
            f.close()
    if dropped:
        flags["route_points_dropped"] = dropped
    return SampleSeries("route", cols) if cols["t"] else None

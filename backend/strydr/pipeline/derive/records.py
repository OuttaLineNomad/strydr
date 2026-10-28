"""Best efforts and records (AD-7), from GPS route distance and time. Runs only (FR-7a)."""
from collections.abc import Mapping, Sequence

from strydr.pipeline.derive import track
from strydr.pipeline.derive.summary import RunFacts

DISTANCES_M = {"1km": 1000.0, "1mi": 1609.344, "5km": 5000.0, "10km": 10000.0, "half": 21097.5, "marathon": 42195.0}
MAX_DISTANCE_ERROR = 0.10  # GPS track length vs the watch's distance; beyond this the track is not trusted
AVG_PACE_MIN_M = 3000.0  # shorter runs are not eligible for the best-average-pace record


def gps_trustworthy(track_m: float, reported_m: float | None) -> bool:
    return reported_m is None or reported_m <= 0 or abs(track_m - reported_m) / reported_m <= MAX_DISTANCE_ERROR


def best_efforts(dist: Sequence[float], t: Sequence[float], reported_m: float | None) -> dict[str, float]:
    if len(dist) < 2 or not gps_trustworthy(dist[-1], reported_m):
        return {}
    out = {}
    for key, metres in DISTANCES_M.items():
        if dist[-1] < metres:
            break
        best = track.best_time(dist, t, metres)
        if best is not None:
            out[key] = best
    return out


SPLIT_UNITS = {"1km": "km", "1mi": "mi"}


def best_from_splits(own: Mapping[str, Sequence], efforts: dict[str, float]) -> dict[str, float]:
    """The 1 km and 1 mile bests are the watch's fastest full split, so they match what the watch shows.

    The GPS rolling window can disagree with the watch's own distance over short stretches; longer
    distances, which the watch does not split, keep the GPS value.
    """
    out = dict(efforts)
    size = {"km": 1000.0, "mi": 1609.344}
    for key, unit in SPLIT_UNITS.items():
        full = [t for u, d, t in zip(own["unit"], own["distance_m"], own["duration_s"]) if u == unit and d >= size[unit] - 1.0]
        if full:
            out[key] = min(full)
        else:
            out.pop(key, None)
    return out


def build_records(runs: Sequence[RunFacts], efforts: Mapping[str, Mapping[str, float]], periods: Sequence[dict]) -> list[dict]:
    by_id = {r.workout_id: r for r in runs}
    out = []
    for key in DISTANCES_M:
        cands = [(e[key], wid) for wid, e in efforts.items() if key in e]
        if cands:
            time_s, wid = min(cands)
            out.append(_rec(f"best_{key}", time_s, "s", by_id[wid]))
    if runs:
        out.append(_rec("longest_run", max(r.distance_m for r in runs), "m", max(runs, key=lambda r: r.distance_m)))
    fast = [r for r in runs if r.distance_m >= AVG_PACE_MIN_M and r.duration_s > 0]
    if fast:
        best = max(fast, key=lambda r: r.distance_m / r.duration_s)
        out.append(_rec("best_avg_pace", best.distance_m / best.duration_s, "m/s", best))
    # Dashboard "Latest vs PR" inputs (FR-9): the most recent run eligible for the same record. `runs` is chronological.
    with_mile = [r for r in runs if "1mi" in efforts.get(r.workout_id, {})]
    if with_mile:
        out.append(_rec("latest_1mi", DISTANCES_M["1mi"] / efforts[with_mile[-1].workout_id]["1mi"], "m/s", with_mile[-1]))
    if fast:
        out.append(_rec("latest_avg_pace", fast[-1].distance_m / fast[-1].duration_s, "m/s", fast[-1]))
    for kind in ("week", "month"):
        ps = [p for p in periods if p["kind"] == kind]
        if ps:
            top = max(ps, key=lambda p: p["distance_m"])
            out.append({"key": f"record_{kind}", "value": top["distance_m"], "unit": "m", "workout_id": None,
                        "local_date": top["start_date"], "period_id": top["period_id"]})
    return out


def _rec(key: str, value: float, unit: str, run: RunFacts) -> dict:
    return {"key": key, "value": value, "unit": unit, "workout_id": run.workout_id,
            "local_date": run.local_date, "period_id": None}

"""Same-route detection and clustering (FR-22, AD-6). Pure and deterministic: no DB, clock or I/O.

Two stages: a cheap prefilter (start/end proximity, distance), then shape confirmation (corridor
overlap both ways, then a discrete Frechet check for order and direction). A reverse run is a
separate route linked as a sibling. `route_key` is the `workout_id` of the route's earliest run.
"""
import tomllib
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString

from strydr.pipeline.derive.routes import geo
from strydr.sources.canonical import Workout

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "routes.toml"
OVERRIDE_KINDS = ("join", "split")


@dataclass(frozen=True)
class RouteThresholds:
    """Every tunable in the `routes` section of config/routes.toml, flattened."""

    # match
    workout_types: tuple[str, ...] = ("run",)
    min_run_length_m: float = 1000.0
    min_gps_coverage: float = 0.80
    max_gps_gap_s: float = 60.0
    start_end_radius_m: float = 150.0
    distance_tolerance_frac: float = 0.15
    distance_tolerance_floor_m: float = 250.0
    resample_spacing_m: float = 10.0
    corridor_m: float = 50.0
    corridor_min_frac: float = 0.90
    frechet_max_m: float = 100.0
    min_runs: int = 2
    medoid_sample_stride: int = 10
    # sections
    split_unit_m_metric: float = 1000.0
    split_unit_m_imperial: float = 1609.344
    split_min_tail_frac: float = 0.5
    min_hr_section_s: float = 180.0
    hr_lag_s: float = 30.0
    hr_sample_span_s: float = 60.0
    min_hr_samples: int = 3
    progress_window_back: int = 3
    progress_window_fwd: int = 60
    boundary_tolerance_m: float = 30.0
    pause_s: float = 30.0
    pause_speed_mps: float = 0.3
    # climbs
    smoothing_window_m: float = 100.0
    pivot_prominence_m: float = 3.0
    merge_gap_m: float = 100.0
    min_length_m: float = 300.0
    min_avg_grade: float = 0.03
    min_gain_m: float = 15.0
    flat_grade: float = 0.01
    # compare
    window_days: int = 180
    hr_match_bpm: float = 4.0
    compare_min_runs: int = 3
    min_gap_s: float = 15.0
    min_gap_frac: float = 0.05
    z_min: float = 2.0
    z_min_small_n: float = 2.5
    small_n_below: int = 5
    max_per_run: int = 2


# keys that would collide with another table's once flattened
_RENAMED = {("compare", "min_runs"): "compare_min_runs"}


def load_thresholds(path: Path | str | None = None) -> RouteThresholds:
    """Read the `routes` section of routes.toml. Unknown keys are an error; missing keys use defaults."""
    with open(path or CONFIG_PATH, "rb") as f:
        section = tomllib.load(f).get("routes", {})
    known = {f.name for f in fields(RouteThresholds)}
    flat: dict = {}
    for table, values in section.items():
        for key, value in values.items():
            name = _RENAMED.get((table, key), key)
            if name not in known:
                raise ValueError(f"unknown routes threshold {table}.{key}")
            flat[name] = tuple(value) if isinstance(value, list) else value
    return RouteThresholds(**flat)


@dataclass(frozen=True, eq=False)
class RoutePath:
    """A run's GPS track prepared for matching. `xy` is resampled; `raw_xy` keeps GPS fixes."""

    workout_id: str
    start_utc: datetime
    origin: tuple[float, float]  # (lat, lon) of the first fix; the local metre frame's zero
    start_ll: tuple[float, float]
    end_ll: tuple[float, float]
    raw_xy: np.ndarray
    t: np.ndarray  # seconds since workout start, per raw fix
    xy: np.ndarray  # resampled to the configured spacing
    cum: np.ndarray  # distance along `xy`
    alt: np.ndarray  # resampled altitude, NaN when missing
    distance_m: float

    @property
    def length_m(self) -> float:
        return float(self.cum[-1])


@dataclass(frozen=True)
class MatchScore:
    direction: str  # same | reverse
    corridor_frac: float  # the lower of the two directions
    frechet_m: float
    distance_ratio: float  # candidate distance / reference distance


def build_path(w: Workout, th: RouteThresholds) -> RoutePath | None:
    """Prepare a workout for matching; None when it is not eligible (type, no GPS, too short, gappy)."""
    if w.type not in th.workout_types or w.is_indoor:
        return None
    series = w.series.get("route")
    if series is None or series.n < 2:
        return None
    c = series.columns
    t = np.asarray(c["t"], dtype=float)
    span = float(t[-1] - t[0])
    if span <= 0:
        return None
    dts = np.diff(t)
    gap_s = float(dts[dts > th.max_gps_gap_s].sum())
    if 1.0 - gap_s / span < th.min_gps_coverage:
        return None
    lat, lon = np.asarray(c["lat"], dtype=float), np.asarray(c["lon"], dtype=float)
    origin = (float(lat[0]), float(lon[0]))
    raw = geo.project(lat, lon, origin)
    alt = np.array([np.nan if a is None else a for a in c.get("alt", [None] * len(t))], dtype=float)
    try:
        xy, cum, alt_r = geo.resample(raw, th.resample_spacing_m, alt)
    except ValueError:
        return None
    distance = float(w.distance_m) if w.distance_m else float(cum[-1])
    if distance < th.min_run_length_m:
        return None
    return RoutePath(
        workout_id=w.workout_id, start_utc=w.start_utc, origin=origin,
        start_ll=(float(lat[0]), float(lon[0])), end_ll=(float(lat[-1]), float(lon[-1])),
        raw_xy=raw, t=t, xy=xy, cum=cum, alt=alt_r, distance_m=distance,
    )


def align_offset(ref: RoutePath, other: RoutePath) -> np.ndarray:
    """Vector that moves `other`'s local frame into `ref`'s frame (their origins are metres apart)."""
    return geo.project([other.origin[0]], [other.origin[1]], ref.origin)[0]


def match_paths(ref: RoutePath, cand: RoutePath, th: RouteThresholds) -> MatchScore | None:
    """Does `cand` repeat `ref` (same direction) or run it backwards? None when neither."""
    fwd = cand.xy + align_offset(ref, cand)
    ref_line = LineString(ref.xy)
    for direction, xy, s_ll, e_ll in (
        ("same", fwd, cand.start_ll, cand.end_ll),
        ("reverse", fwd[::-1], cand.end_ll, cand.start_ll),
    ):
        # stage A: prefilter
        if geo.haversine_m(*ref.start_ll, *s_ll) > th.start_end_radius_m:
            continue
        if geo.haversine_m(*ref.end_ll, *e_ll) > th.start_end_radius_m:
            continue
        tol = max(th.distance_tolerance_frac * ref.distance_m, th.distance_tolerance_floor_m)
        if abs(cand.distance_m - ref.distance_m) > tol:
            continue
        # stage B: corridor overlap both ways, then order/direction on the in-corridor points
        cand_line = LineString(xy)
        in_c = shapely.distance(shapely.points(xy), ref_line) <= th.corridor_m
        in_r = shapely.distance(shapely.points(ref.xy), cand_line) <= th.corridor_m
        frac = min(float(in_c.mean()), float(in_r.mean()))
        if frac < th.corridor_min_frac or in_c.sum() < 2 or in_r.sum() < 2:
            continue
        fd = float(shapely.frechet_distance(LineString(ref.xy[in_r]), LineString(xy[in_c])))
        if fd > th.frechet_max_m:
            continue
        return MatchScore(direction, frac, fd, cand.distance_m / ref.distance_m)
    return None


def _mean_offset(a: RoutePath, b: RoutePath, stride: int) -> float:
    """Symmetric mean distance between two same-direction paths (the medoid metric)."""
    bxy = b.xy + align_offset(a, b)
    d1 = shapely.distance(shapely.points(bxy[::stride]), LineString(a.xy)).mean()
    d2 = shapely.distance(shapely.points(a.xy[::stride]), LineString(bxy)).mean()
    return float((d1 + d2) / 2)


@dataclass(frozen=True)
class RouteCluster:
    route_key: str  # workout_id of the earliest run
    member_ids: tuple[str, ...]  # chronological
    reference_id: str  # medoid run
    sibling_key: str | None  # route_key of the reverse-direction route, if any
    reference_length_m: float
    scores: dict[str, MatchScore]  # member vs reference, for threshold calibration


class _Route:
    def __init__(self, members: list[RoutePath]):
        self.members = members
        self.ref = members[0]

    @property
    def key(self) -> str:
        return self.members[0].workout_id


def _parse_overrides(overrides: Iterable[tuple[str, str, str]]) -> dict[frozenset, str]:
    out: dict[frozenset, str] = {}
    for a, b, kind in overrides:
        if kind not in OVERRIDE_KINDS:
            raise ValueError(f"unknown route override kind {kind!r}")
        out[frozenset((a, b))] = kind  # a later entry for the same pair wins
    return out


def cluster(
    workouts: Sequence[Workout],
    overrides: Iterable[tuple[str, str, str]] = (),
    th: RouteThresholds | None = None,
) -> list[RouteCluster]:
    """Group runs into routes. The result does not depend on input order.

    Runs are placed chronologically; each joins the best-matching existing route (compared with that
    route's medoid) or starts a new one. `join` overrides bind runs (transitively) into one unit that
    is placed together; `split` overrides forbid two runs from sharing a route. Only routes with at
    least `min_runs` runs are returned, ordered by route_key.
    """
    th = th or load_thresholds()
    pair_kind = _parse_overrides(overrides)
    seen: dict[str, RoutePath] = {}
    for w in workouts:
        p = build_path(w, th)
        if p is not None:
            seen.setdefault(w.workout_id, p)
    paths = sorted(seen.values(), key=lambda p: (p.start_utc, p.workout_id))

    parent = {p.workout_id: p.workout_id for p in paths}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pair, kind in pair_kind.items():
        if kind == "join" and len(pair) == 2 and all(i in parent for i in pair):
            a, b = sorted(pair)
            parent[find(b)] = find(a)
    units: dict[str, list[RoutePath]] = {}
    for p in paths:
        units.setdefault(find(p.workout_id), []).append(p)
    ordered = sorted(units.values(), key=lambda u: (u[0].start_utc, u[0].workout_id))

    splits = {pair for pair, kind in pair_kind.items() if kind == "split"}
    dist_cache: dict[tuple[str, str], float] = {}

    def pair_d(a: RoutePath, b: RoutePath) -> float:
        k = (a.workout_id, b.workout_id) if a.workout_id < b.workout_id else (b.workout_id, a.workout_id)
        if k not in dist_cache:
            dist_cache[k] = _mean_offset(a, b, th.medoid_sample_stride)
        return dist_cache[k]

    def medoid(members: list[RoutePath]) -> RoutePath:
        if len(members) < 3:
            return members[0]
        return min(
            members,
            key=lambda m: (round(sum(pair_d(m, o) for o in members if o is not m), 6), m.start_utc, m.workout_id),
        )

    routes: list[_Route] = []
    for unit in ordered:
        ids = [p.workout_id for p in unit]
        best: tuple[float, str, _Route] | None = None
        for r in routes:
            if any(frozenset((u, m.workout_id)) in splits for u in ids for m in r.members):
                continue
            ms = match_paths(r.ref, unit[0], th)
            if ms is None or ms.direction != "same":
                continue
            if best is None or (ms.frechet_m, r.key) < best[:2]:
                best = (ms.frechet_m, r.key, r)
        if best is None:
            r = _Route(list(unit))
            routes.append(r)
        else:
            r = best[2]
            r.members = sorted(r.members + unit, key=lambda p: (p.start_utc, p.workout_id))
        r.ref = medoid(r.members)

    kept = sorted((r for r in routes if len(r.members) >= th.min_runs), key=lambda r: r.key)
    siblings = _link_siblings(kept, th)
    out = []
    for r in kept:
        scores = {}
        for m in r.members:
            ms = MatchScore("same", 1.0, 0.0, 1.0) if m is r.ref else match_paths(r.ref, m, th)
            if ms is not None:
                scores[m.workout_id] = ms
        out.append(RouteCluster(
            route_key=r.key,
            member_ids=tuple(m.workout_id for m in r.members),
            reference_id=r.ref.workout_id,
            sibling_key=siblings.get(r.key),
            reference_length_m=r.ref.length_m,
            scores=scores,
        ))
    return out


def _link_siblings(routes: list[_Route], th: RouteThresholds) -> dict[str, str]:
    """Pair each route with the route that runs the same line backwards (at most one each)."""
    cands = []
    for i, a in enumerate(routes):
        for b in routes[i + 1:]:
            ms = match_paths(a.ref, b.ref, th)
            if ms is not None and ms.direction == "reverse":
                cands.append((ms.frechet_m, a.key, b.key))
    links: dict[str, str] = {}
    for _, ka, kb in sorted(cands):
        if ka not in links and kb not in links:
            links[ka], links[kb] = kb, ka
    return links

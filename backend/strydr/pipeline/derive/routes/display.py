"""The only producer of geometry the API may serve (AD-10)."""
import math
from collections.abc import Mapping, Sequence

M_PER_DEG = 111_320.0
MIN_STEP_M = 8.0  # thins the 1 Hz track to what a map can show


def _inside(lat: float, lon: float, zone) -> bool:
    """Clip circle: centred on the zone centre shifted by its stored offset, radius = radius + trim (AD-10)."""
    cos = math.cos(math.radians(zone.lat))
    dy = (lat - zone.lat) * M_PER_DEG - zone.offset_north_m
    dx = (lon - zone.lon) * M_PER_DEG * cos - zone.offset_east_m
    return math.hypot(dx, dy) <= zone.radius_m + zone.trim_m


def _walk_segments(segments: list[list[list[float]]], flags: list[list[bool]]) -> list[list[list[float]]]:
    """Runs of consecutive walk points inside one clipped segment; each run keeps the next point so it joins the line."""
    out = []
    for seg, fl in zip(segments, flags):
        i = 0
        while i < len(seg):
            if not fl[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(seg) and fl[j + 1]:
                j += 1
            piece = seg[i:j + 2]
            if len(piece) >= 2:
                out.append(piece)
            i = j + 1
    return out


def for_display(geometry: Mapping[str, Sequence], zones: Sequence, walk_ranges: Sequence[Sequence[float]] | None = None) -> dict | None:
    """Clip every point inside any zone and derive start, end and bounds from what remains.

    `geometry` holds equal-length `lat` and `lon` columns. The result is None when no point survives.
    `walk_ranges` ([t0, t1] on the geometry's active clock, its `at` column; without one there are none) marks walking sections:
    `walk_segments` is cut from the same clipped points, so nothing inside a zone can appear in it (AD-10)."""
    segments: list[list[list[float]]] = []
    flags: list[list[bool]] = []
    current: list[list[float]] = []
    cur_flags: list[bool] = []
    last = None
    clock = geometry.get("at") or [0.0] * len(geometry["lat"])
    ranges = sorted(tuple(r) for r in walk_ranges or ()) if geometry.get("at") else []  # no active clock, no walk overlay
    for lat, lon, at in zip(geometry["lat"], geometry["lon"], clock):
        if any(_inside(lat, lon, z) for z in zones):
            if current:
                segments.append(current)
                flags.append(cur_flags)
            current, cur_flags, last = [], [], None
            continue
        if last is not None and math.hypot((lat - last[0]) * M_PER_DEG,
                                           (lon - last[1]) * M_PER_DEG * math.cos(math.radians(lat))) < MIN_STEP_M:
            continue
        current.append([round(lat, 5), round(lon, 5)])
        cur_flags.append(any(a <= at < b for a, b in ranges))
        last = (lat, lon)
    if current:
        segments.append(current)
        flags.append(cur_flags)
    points = [p for seg in segments for p in seg]
    if not points:
        return None
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    return {
        "segments": segments,
        "start": segments[0][0],
        "end": segments[-1][-1],
        "bounds": [min(lats), min(lons), max(lats), max(lons)],
        "walk_segments": _walk_segments(segments, flags),
    }

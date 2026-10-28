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


def for_display(geometry: Mapping[str, Sequence], zones: Sequence) -> dict | None:
    """Clip every point inside any zone and derive start, end and bounds from what remains.

    `geometry` holds equal-length `lat` and `lon` columns. The result is None when no point survives."""
    segments: list[list[list[float]]] = []
    current: list[list[float]] = []
    last = None
    for lat, lon in zip(geometry["lat"], geometry["lon"]):
        if any(_inside(lat, lon, z) for z in zones):
            if current:
                segments.append(current)
            current, last = [], None
            continue
        if last is not None and math.hypot((lat - last[0]) * M_PER_DEG,
                                           (lon - last[1]) * M_PER_DEG * math.cos(math.radians(lat))) < MIN_STEP_M:
            continue
        current.append([round(lat, 5), round(lon, 5)])
        last = (lat, lon)
    if current:
        segments.append(current)
    points = [p for seg in segments for p in seg]
    if not points:
        return None
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    return {
        "segments": segments,
        "start": segments[0][0],
        "end": segments[-1][-1],
        "bounds": [min(lats), min(lons), max(lats), max(lons)],
    }

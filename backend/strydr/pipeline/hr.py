"""Time-weighted heart rate (shared by derive and profile; neither imports the other).

HR arrives at any density: per-minute buckets, sparse readings, or one reading every few seconds. Every
sample is weighted by the time it covers, so the density of the export never changes a result.

Callers pass `active_clock(series)` as the time axis, not wall-clock `t`: readings taken during a pause share one
active time, get zero step, and so add no zone, load or HRmax time."""
from collections.abc import Mapping, Sequence
from statistics import median, median_low

HR_MIN, HR_MAX = 25, 250  # bpm; a reading outside this is impossible and counts as no time
MAX_STEP_S = 120.0  # same cap as thresholds.toml max_step_s: a longer gap counts only the cap, never forward-filled
DEFAULT_STEP_S = 60.0  # a lone sample
MINUTE_S = 60.0


def active_clock(series: Mapping[str, Sequence]) -> Sequence[float]:
    """The series' active-time clock `at` (pauses removed), or wall-clock `t` when `at` is missing or empty."""
    return series.get("at") or series["t"]


def sample_steps(t: Sequence[float], avg: Sequence[float]) -> list[float]:
    """Seconds each sample covers, returned in the caller's order (t need not be sorted).

    A sample covers the time to the next one by time, capped; the last covers the typical step. When the
    typical step is a minute or more the series is buckets, and no step exceeds that typical step (a missing
    minute does not stretch its neighbour); for readings the cap is MAX_STEP_S.
    Steps are measured on the full timeline, so an impossible reading (step 0) leaves a gap rather than
    letting its neighbours stretch across it."""
    n = len(t)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: t[i])
    ts = [t[i] for i in order]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not gaps:
        cap = last = DEFAULT_STEP_S
    elif median_low(gaps) >= DEFAULT_STEP_S:
        cap = last = min(median_low(gaps), MAX_STEP_S)
    else:
        cap, last = MAX_STEP_S, min(median(gaps), MAX_STEP_S)
    out = [0.0] * n
    for k, i in enumerate(order):
        step = (ts[k + 1] - ts[k]) if k + 1 < n else last
        step = min(max(step, 0.0), cap)
        out[i] = step if HR_MIN <= avg[i] <= HR_MAX else 0.0
    return out


def minute_bins(t: Sequence[float], avg: Sequence[float]) -> dict[int, tuple[float, float]]:
    """Per minute bin `int(t // 60)`: (time-weighted mean HR, seconds covered). A minute with no valid time is absent."""
    sums: dict[int, list[float]] = {}
    for ti, a, w in zip(t, avg, sample_steps(t, avg)):
        if w > 0:
            acc = sums.setdefault(int(ti // MINUTE_S), [0.0, 0.0])
            acc[0] += a * w
            acc[1] += w
    return {m: (s / w, w) for m, (s, w) in sums.items()}


def minute_means(t: Sequence[float], avg: Sequence[float]) -> dict[int, float]:
    """Time-weighted mean HR per minute bin."""
    return {m: mean for m, (mean, _) in minute_bins(t, avg).items()}

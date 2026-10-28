"""Generate FULLY SYNTHETIC Health Auto Export-shaped JSON fixtures.

Everything here is invented: fake source, arbitrary city, fixed fake dates, seeded noise.
Structure mirrors a Health Auto Export (iOS app) REST API JSON payload.
Run: python generate_hae_export.py   (writes the files next to this script)
"""
import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent
TZ = timezone(timedelta(hours=-5))
SOURCE = {"identifier": "com.example.synthetic.00000000-0000-0000-0000-000000000000", "name": "Synthetic Watch"}
CENTER = (52.3700, 4.8900)  # arbitrary city centre; the route is a made-up loop
MI, FT, KMH = 1609.344, 0.3048, 1000 / 3600


def wid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"strydr-fixture-{label}")).upper()


def ts(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %z")


def q(qty, units):
    return {"qty": qty, "units": units}


def route(start: datetime, seconds: int, speed_mps: float, seed: int) -> list[dict]:
    rnd = random.Random(seed)
    pts, heading, lat, lon = [], rnd.uniform(0, 6.28), CENTER[0], CENTER[1]
    for i in range(seconds):
        heading += 0.004 + rnd.uniform(-0.002, 0.002)
        v = speed_mps * (1 + rnd.uniform(-0.05, 0.05))
        lat += v * math.cos(heading) / 111_320
        lon += v * math.sin(heading) / (111_320 * math.cos(math.radians(lat)))
        pts.append({
            "timestamp": ts(start + timedelta(seconds=i)), "latitude": round(lat, 6), "longitude": round(lon, 6),
            "altitude": round(3 + 6 * math.sin(i / 90) + rnd.uniform(-0.4, 0.4), 2),
            "speed": round(v, 2), "course": round(math.degrees(heading) % 360, 1),
            "horizontalAccuracy": 5.0, "verticalAccuracy": 3.0, "speedAccuracy": 0.5, "courseAccuracy": 10.0,
        })
    return pts


def hr_series(start: datetime, minutes: int, base: int, seed: int, *, seconds=False, dropout=None) -> list[dict]:
    """Per-minute buckets, or with seconds=True one reading per 1-9 s (Min = Avg = Max).

    dropout=(from_s, to_s) leaves no readings in that window."""
    rnd = random.Random(seed)
    out = []
    if seconds:
        t = 0.0
        while t < minutes * 60:
            v = int(round(base + 6 * math.sin(t / 240) + rnd.uniform(-2, 2)))  # drawn on every step, dropout or not
            if not dropout or not dropout[0] <= t < dropout[1]:
                out.append({"date": ts(start + timedelta(seconds=t)), "Min": v, "Avg": v, "Max": v, "units": "count/min"})
            t += rnd.randint(1, 9)
        return out
    for m in range(minutes):
        avg = base + 6 * math.sin(m / 4) + rnd.uniform(-2, 2)
        out.append({"date": ts(start + timedelta(minutes=m, seconds=30)), "Min": int(avg - 4), "Avg": round(avg, 2),
                    "Max": int(avg + 5), "units": "count/min"})
    return out


def split_set(unit: str, size_m: float, total_m: float, pace_s_per_m: float) -> dict:
    items, n, t = [], int(math.ceil(total_m / size_m)), 0.0
    for i in range(n):
        d = min(size_m, total_m - i * size_m)
        items.append({"index": i, "activeDuration": d * pace_s_per_m, "isPartial": d < size_m,
                      "metrics": {"distance": {"qty": d, "units": "m", "origin": "activityStatistics"}}})
    return {"distanceType": "walkingRunning", "boundaryOrigin": "distanceInterpolation",
            "targetDistance": {"qty": 1, "units": unit}, "items": items}


def workout(label, name, activity, code, start, minutes, speed_mps, *, indoor=False, hr=True, with_route=True,
            with_id=True, distance_units="mi", temp=("degF", 41.0), seed=0, base_hr=140, hr_seconds=False,
            hr_dropout=None) -> dict:
    seconds = minutes * 60
    dist_m = speed_mps * seconds
    w = {
        "name": name, "location": "Indoor" if indoor else "Outdoor", "isIndoor": indoor,
        "start": ts(start), "end": ts(start + timedelta(seconds=seconds + 45)), "duration": float(seconds),
        "source": SOURCE, "metadata": {},
        "activeEnergyBurned": q(round(seconds * 0.12, 1), "kcal"), "totalEnergy": q(round(seconds * 0.14, 1), "kcal"),
        "distance": q(round(dist_m / (MI if distance_units == "mi" else 1000), 3), distance_units),
        "speed": q(round(speed_mps / 0.44704, 2), "mi/hr"),
        "stepCadence": q(round(speed_mps * 26, 1), "count/min"),
        "intensity": q(4.2, "kcal/hr·kg"),
        "activities": [{"index": 0, "activityType": activity, "activityTypeCode": code,
                        "configuration": {"locationType": "indoor" if indoor else "outdoor"}}],
        "splits": [split_set("km", 1000, dist_m, 1 / speed_mps), split_set("mi", MI, dist_m, 1 / speed_mps)],
    }
    if with_id:
        w["id"] = wid(label)
        w["activities"][0]["id"] = w["id"]
    if hr:
        w["avgHeartRate"] = q(base_hr, "count/min")
        w["maxHeartRate"] = q(base_hr + 18, "count/min")
        w["heartRate"] = {k: q(v, "count/min") for k, v in (("min", base_hr - 20), ("avg", base_hr), ("max", base_hr + 18))}
        w["heartRateData"] = hr_series(start, minutes, base_hr, seed, seconds=hr_seconds, dropout=hr_dropout)
    if not indoor:
        w["avgSpeed"] = q(round(speed_mps / 0.44704, 2), "mi")  # sic: HAE labels a speed "mi"
        w["maxSpeed"] = q(round(speed_mps * 1.2 / 0.44704, 2), "mi")
        w["elevationUp"] = q(round(30 / FT, 1), "ft")
        w["temperature"] = q(temp[1], temp[0])
        w["humidity"] = q(62, "%")
        w["effortScore"] = q(5, "appleEffortScore")
    else:
        w["estimatedEffortScore"] = q(3, "appleEffortScore")
    if with_route and not indoor:
        w["route"] = route(start, seconds, speed_mps, seed)
    return w


def metric_points(start_day: datetime, values: list, key="qty", skip=()) -> list[dict]:
    return [{"date": ts(start_day + timedelta(days=i)), key: v, "source": "Synthetic Watch"}
            for i, v in enumerate(values) if i not in skip]


def metrics() -> list[dict]:
    d0 = datetime(2026, 3, 1, 0, 0, 0, tzinfo=TZ)
    hr = [{"date": ts(d0 + timedelta(days=i)), "Min": 48 + i, "Avg": 70 + i, "Max": 150 + i} for i in range(7)]
    sleep = [{"date": ts(d0 + timedelta(days=i)), "source": "Synthetic Watch", "totalSleep": 7.0 + i / 10,
              "asleep": 0, "core": 4.0, "deep": 1.0, "rem": 1.5, "awake": 0.4, "inBed": 0,
              "sleepStart": ts(d0 + timedelta(days=i, hours=-1)), "sleepEnd": ts(d0 + timedelta(days=i, hours=7)),
              "inBedStart": ts(d0 + timedelta(days=i, hours=-1)), "inBedEnd": ts(d0 + timedelta(days=i, hours=7))}
             for i in range(5)]
    return [
        {"name": "heart_rate", "units": "count/min", "data": hr},
        {"name": "resting_heart_rate", "units": "count/min", "data": metric_points(d0, [52, 53, 51, 54, 52, 55, 53], skip=(2,))},
        {"name": "heart_rate_variability", "units": "ms", "data": metric_points(d0, [61, 58.5, 64, 60, 57, 66, 62])},
        {"name": "walking_running_distance", "units": "mi", "data": metric_points(d0, [3.1, 2.0, 1.2, 2.2, 4.0, 1.0, 2.5])},
        {"name": "walking_speed", "units": "mi/hr", "data": metric_points(d0, [3.0, 3.1, 2.9], skip=())},
        {"name": "walking_step_length", "units": "in", "data": metric_points(d0, [27.5, 27.0, 28.1])},
        {"name": "weight_body_mass", "units": "lb", "data": metric_points(d0, [170.0, 169.4])},
        {"name": "apple_sleeping_wrist_temperature", "units": "degF", "data": metric_points(d0, [96.8, 97.1, 96.5])},
        {"name": "six_minute_walking_test_distance", "units": "m", "data": metric_points(d0, [510])},
        {"name": "step_count", "units": "count", "data": metric_points(d0, [8123, 5400, 3000, 6200, 11000, 2500, 7000])},
        {"name": "sleep_analysis", "units": "hr", "data": sleep},
    ]


def export(workouts: list[dict], with_metrics=True) -> dict:
    return {"data": {"metrics": metrics() if with_metrics else [], "workouts": workouts}}


def build() -> dict[str, dict]:
    t = lambda d, h, m: datetime(2026, 3, d, h, m, 0, tzinfo=TZ)
    run = workout("run", "Outdoor Run", "running", 37, t(3, 7, 30), 25, 3.2, seed=1, base_hr=158)
    run["heartRateData"][4]["Max"] = 320  # impossible sample: dropped and counted in quality_flags
    walk_a = workout("walk-a", "Outdoor Walk", "walking", 52, t(4, 17, 40), 18, 1.4, seed=2, base_hr=112)
    walk_nohr = workout("walk-nohr", "Outdoor Walk", "walking", 52, t(5, 12, 5), 15, 1.3, hr=False, seed=3)
    walk_thin = workout("walk-richer", "Outdoor Walk", "walking", 52, t(6, 16, 15), 20, 1.5, with_route=False, seed=4, base_hr=108)
    walk_noid = workout("walk-noid", "Outdoor Walk", "walking", 52, t(7, 8, 0), 12, 1.4, with_id=False, seed=5, base_hr=105)
    indoor = workout("walk-indoor", "Indoor Walk", "walking", 52, t(2, 18, 0), 30, 1.2, indoor=True, seed=6, base_hr=110)
    hike = workout("hike", "Outdoor Hike", "hiking", 24, t(8, 9, 0), 40, 1.1, distance_units="km",
                   temp=("degC", 4.0), seed=7, base_hr=125)
    bike = workout("bike", "Outdoor Cycling", "cycling", 13, t(8, 15, 0), 20, 6.0, seed=8)
    richer = workout("walk-richer", "Outdoor Walk", "walking", 52, t(6, 16, 15), 20, 1.5, seed=4, base_hr=108)
    secs = workout("run-seconds", "Outdoor Run", "running", 37, t(9, 7, 30), 25, 3.2, seed=9, base_hr=158,
                   hr_seconds=True, hr_dropout=(600, 960))
    return {
        "hae-export.json": export([indoor, run, walk_a, walk_nohr, walk_thin, walk_noid, hike, bike]),
        # Same run re-exported in a later window: identical content, different payload bytes.
        "hae-resend.json": export([run], with_metrics=False) | {"window": "re-run"},
        # A richer copy (adds the route) of a workout that is thin in hae-export.json.
        "hae-richer.json": export([richer], with_metrics=False),
        # HAE at seconds aggregation: one HR reading every 1-9 s, with a 6-minute dropout.
        "hae-seconds.json": export([secs], with_metrics=False),
    }


if __name__ == "__main__":
    for name, doc in build().items():
        (OUT / name).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {name}")

"""Fully synthetic demo data for the docs screenshots: a made-up runner in Central Park, NYC.

Writes HAE-shaped JSON batches, a metrics payload and the home-workout session times into the folder given as the
first argument (default ./out). Nothing here comes from a real person: routes are drawn loops, everything else is seeded.
Run: python generate.py [out_dir]
"""
import json
import math
import random
import sys
import uuid
import zlib
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out"
SOURCE = {"identifier": "com.example.demo.watch", "name": "Demo Watch"}
MI = 1609.344
R = random.Random(42)
START = date(2026, 6, 15)  # a Monday
END = date(2026, 11, 3)


def wid(label):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"strydr-demo-{label}")).upper()


def ts(dt):
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %z")


def q(v, u):
    return {"qty": v, "units": u}


# Route shapes: closed polylines (lat, lon, alt_m) the runner follows, sampled by distance.
def ellipse(c, a_m, b_m, rot, n=400, hill=None):
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        x, y = a_m * math.cos(th), b_m * math.sin(th)
        x, y = x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
        # gentle wobble so it does not look like a perfect ellipse
        x += 25 * math.sin(5 * th); y += 18 * math.cos(3 * th)
        alt = 30 + (hill(th) if hill else 2 * math.sin(2 * th))
        pts.append((c[0] + y / 111_320, c[1] + x / (111_320 * math.cos(math.radians(c[0]))), alt))
    pts.append(pts[0])
    return pts


def line(a, b, n=200):
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, 4 + 1.5 * math.sin(i / 15)) for i in range(n + 1)]


RESERVOIR = ellipse((40.7851, -73.9620), 520, 330, math.radians(61))
PARK_LOOP = ellipse((40.7826, -73.9656), 1950, 330, math.radians(61), n=900,
                    hill=lambda th: 22 * max(0, math.cos(th - 0.3)) ** 3)  # the hill at the north end
RIVER_OUT = line((40.7720, -73.9880), (40.8010, -73.9705))
RIVER = RIVER_OUT + RIVER_OUT[::-1]


def seg_len(p, q_):
    dy = (q_[0] - p[0]) * 111_320
    dx = (q_[1] - p[1]) * 111_320 * math.cos(math.radians(p[0]))
    return math.hypot(dx, dy)


def path_len(path):
    return sum(seg_len(path[i], path[i + 1]) for i in range(len(path) - 1))


def at_distance(path, d):
    d %= path_len(path)
    for i in range(len(path) - 1):
        L = seg_len(path[i], path[i + 1])
        if d <= L:
            f = d / L if L else 0
            return tuple(path[i][k] + (path[i + 1][k] - path[i][k]) * f for k in range(3))
        d -= L
    return path[-1]


def run_workout(label, start, path, laps, pace_s_mi, base_hr, temp_f, hum, *, kind="running", seed=0, carry=False):
    rnd = random.Random(seed)
    total_m = path_len(path) * laps
    speed = MI / pace_s_mi
    seconds = int(total_m / speed)
    pts, hr, steps, d = [], [], [], 0.0
    prev_alt = None
    gain = 0.0
    ox = oy = 0.0
    for s in range(seconds):
        lat, lon, alt = at_distance(path, d)
        grade = 0 if prev_alt is None else (alt - prev_alt)
        if prev_alt is not None and alt > prev_alt:
            gain += alt - prev_alt
        prev_alt = alt
        v = speed * (1 + rnd.uniform(-0.04, 0.04)) * (1 - 0.6 * grade)
        d += v
        ox = 0.97 * ox + rnd.uniform(-0.15, 0.15) / 111_320
        oy = 0.97 * oy + rnd.uniform(-0.15, 0.15) / 111_320
        pts.append({"timestamp": ts(start + timedelta(seconds=s)), "latitude": round(lat + oy, 6),
                    "longitude": round(lon + ox, 6), "altitude": round(alt + rnd.uniform(-.3, .3), 2),
                    "speed": round(v, 2), "course": 0.0, "horizontalAccuracy": 4.0, "verticalAccuracy": 3.0,
                    "speedAccuracy": 0.4, "courseAccuracy": 8.0})
        warm = min(1, s / 300)
        drift = 0.08 * base_hr * (s / 3600) * (1.4 if temp_f > 78 else 1)
        bpm = int(round(base_hr * (0.82 + 0.18 * warm) + drift + 40 * max(0, grade) + rnd.uniform(-2, 2)))
        if s % rnd.randint(2, 6) == 0:
            hr.append({"date": ts(start + timedelta(seconds=s)), "Min": bpm, "Avg": bpm, "Max": bpm, "units": "count/min"})
        if s % 60 == 0:
            cad = 166 if kind == "running" else 112
            steps.append({"date": ts(start + timedelta(seconds=s)), "qty": round(cad * (1 + rnd.uniform(-.05, .05)), 1),
                          "source": SOURCE["name"], "units": "count"})
    avg = sum(h["Avg"] for h in hr) / len(hr)
    mx = max(h["Avg"] for h in hr)
    name = {"running": "Outdoor Run", "walking": "Outdoor Walk", "hiking": "Outdoor Hike"}[kind]
    code = {"running": 37, "walking": 52, "hiking": 24}[kind]
    return {
        "id": wid(label), "name": name, "location": "Outdoor", "isIndoor": False,
        "start": ts(start), "end": ts(start + timedelta(seconds=seconds + 20)), "duration": float(seconds),
        "source": SOURCE, "metadata": {},
        "activeEnergyBurned": q(round(seconds * 0.19, 1), "kcal"), "totalEnergy": q(round(seconds * 0.22, 1), "kcal"),
        "distance": q(round(total_m / MI, 3), "mi"), "speed": q(round(speed / 0.44704, 2), "mi/hr"),
        "stepCadence": q(166 if kind == "running" else 112, "count/min"), "intensity": q(9.5, "kcal/hr·kg"),
        "activities": [{"index": 0, "activityType": kind, "activityTypeCode": code, "id": wid(label),
                        "configuration": {"locationType": "outdoor"}}],
        "avgHeartRate": q(round(avg), "count/min"), "maxHeartRate": q(mx, "count/min"),
        "heartRate": {"min": q(min(h["Avg"] for h in hr), "count/min"), "avg": q(round(avg), "count/min"), "max": q(mx, "count/min")},
        "heartRateData": hr, "stepCount": steps,
        "avgSpeed": q(round(speed / 0.44704, 2), "mi"), "maxSpeed": q(round(speed * 1.15 / 0.44704, 2), "mi"),
        "elevationUp": q(round(gain / 0.3048, 1), "ft"), "temperature": q(temp_f, "degF"), "humidity": q(hum, "%"),
        "effortScore": q(min(10, max(2, round((base_hr - 120) / 8))), "appleEffortScore"),
        "route": pts,
    }


def strength_workout(label, start, minutes, base_hr, effort, seed):
    rnd = random.Random(seed)
    secs = minutes * 60
    hr = []
    t = 0
    while t < secs:
        bpm = int(base_hr + 18 * math.sin(t / 50) ** 2 + rnd.uniform(-3, 3) - (25 if t < 60 else 0))
        hr.append({"date": ts(start + timedelta(seconds=t)), "Min": bpm, "Avg": bpm, "Max": bpm, "units": "count/min"})
        t += rnd.randint(1, 5)
    return {
        "id": wid(label), "name": "Functional Strength Training", "location": "Indoor", "isIndoor": True,
        "start": ts(start), "end": ts(start + timedelta(seconds=secs)), "duration": float(secs), "source": SOURCE,
        "metadata": {}, "activeEnergyBurned": q(round(secs * .13, 1), "kcal"), "totalEnergy": q(round(secs * .15, 1), "kcal"),
        "intensity": q(5.0, "kcal/hr·kg"),
        "activities": [{"index": 0, "activityType": "functionalStrengthTraining", "activityTypeCode": 20, "id": wid(label),
                        "configuration": {"locationType": "indoor"}}],
        "avgHeartRate": q(base_hr + 8, "count/min"), "maxHeartRate": q(base_hr + 24, "count/min"),
        "heartRate": {"min": q(base_hr - 30, "count/min"), "avg": q(base_hr + 8, "count/min"), "max": q(base_hr + 24, "count/min")},
        "heartRateData": hr, "effortScore": q(effort, "appleEffortScore"),
    }


def temp_for(day):
    # summer peak late July, cooling into November
    doy = day.timetuple().tm_yday
    return round(62 + 22 * math.cos((doy - 205) / 365 * 2 * math.pi) + R.uniform(-5, 5)), R.randint(45, 85)


def build():
    workouts, sessions, days = [], [], []
    d = START
    week = 0
    while d <= END:
        dow = d.weekday()
        fit = (d - START).days / (END - START).days  # 0 -> 1 fitness over the block
        temp, hum = temp_for(d)
        t0 = datetime(d.year, d.month, d.day, 6, 30 + R.randint(0, 25), tzinfo=TZ)
        label = d.isoformat()
        easy_pace = 640 - 45 * fit + (25 if temp > 80 else 0)
        if dow == 1:   # Tue: reservoir, 2 laps
            workouts.append(run_workout(f"{label}-res", t0, RESERVOIR, 2, easy_pace - 15, 138, temp, hum, seed=zlib.crc32(label.encode()) % 999))
        elif dow == 3:  # Thu: tempo-ish on the park loop
            workouts.append(run_workout(f"{label}-loop", t0, PARK_LOOP, 1, easy_pace - 55, 158, temp, hum, seed=zlib.crc32(label.encode()) % 999))
        elif dow == 5:  # Sat: long run, grows over the block
            laps = 1.3 + 1.2 * fit + (0.4 if week == 14 else 0)
            workouts.append(run_workout(f"{label}-long", t0 + timedelta(hours=1), PARK_LOOP, laps, easy_pace + 10, 136, temp, hum,
                                        seed=zlib.crc32(label.encode()) % 999))
        elif dow == 6 and week % 2 == 0:  # Sun: easy river out-and-back, or a walk with the kid
            if week % 4 == 0:
                workouts.append(run_workout(f"{label}-walk", t0 + timedelta(hours=3), RIVER, 1, 1080, 104, temp, hum,
                                            kind="walking", seed=zlib.crc32(label.encode()) % 999))
            else:
                workouts.append(run_workout(f"{label}-river", t0 + timedelta(hours=2), RIVER, 1, easy_pace + 20, 134, temp, hum,
                                            seed=zlib.crc32(label.encode()) % 999))
        if dow in (0, 4) and d >= date(2026, 9, 1):  # Mon/Fri evening home strength, from September
            st = datetime(d.year, d.month, d.day, 18, 30, tzinfo=TZ)
            n = len(sessions)
            workouts.append(strength_workout(f"{label}-str", st - timedelta(minutes=1), 22, 128, 6 if n % 3 else 7, zlib.crc32(label.encode()) % 999))
            sessions.append({"start": st, "n": n, "kind": "swing" if dow == 0 else "push"})
        # daily metrics
        sick = date(2026, 10, 6) <= d <= date(2026, 10, 9)
        rhr = 56 - 4 * fit + R.uniform(-1.5, 1.5) + (7 if sick else 0)
        hrv = 52 + 10 * fit + R.uniform(-6, 6) - (14 if sick else 0)
        sleep_h = 7.4 + R.uniform(-.7, .6) - (1.6 if R.random() < .1 else 0)
        days.append((d, round(rhr, 1), round(hrv, 1), round(sleep_h, 2)))
        d += timedelta(days=1)
        if d.weekday() == 0:
            week += 1
    return workouts, sessions, days


def metrics(days):
    def pts(vals):
        return [{"date": ts(datetime(x.year, x.month, x.day, tzinfo=TZ)), "qty": v, "source": SOURCE["name"]} for x, v in vals]
    sleep = []
    for d, _, _, h in days:
        end = datetime(d.year, d.month, d.day, 6, 15, tzinfo=TZ)
        st = end - timedelta(hours=h + .3)
        sleep.append({"date": ts(datetime(d.year, d.month, d.day, tzinfo=TZ)), "source": SOURCE["name"], "totalSleep": h, "asleep": 0,
                      "core": round(h * .55, 2), "deep": round(h * .17, 2), "rem": round(h * .23, 2), "awake": .3, "inBed": 0,
                      "sleepStart": ts(st), "sleepEnd": ts(end), "inBedStart": ts(st), "inBedEnd": ts(end)})
    return [
        {"name": "resting_heart_rate", "units": "count/min", "data": pts([(d, r) for d, r, _, _ in days])},
        {"name": "heart_rate_variability", "units": "ms", "data": pts([(d, v) for d, _, v, _ in days])},
        {"name": "step_count", "units": "count", "data": pts([(d, R.randint(5000, 13000)) for d, *_ in days])},
        {"name": "weight_body_mass", "units": "lb", "data": pts([(d, round(172 - 4 * i / len(days) + R.uniform(-.6, .6), 1))
                                                                  for i, (d, *_) in enumerate(days) if i % 3 == 0])},
        {"name": "sleep_analysis", "units": "hr", "data": sleep},
    ]


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    workouts, sessions, days = build()
    workouts.sort(key=lambda w: w["start"])
    batch = []
    n = 0
    for w in workouts:
        batch.append(w)
        if len(batch) == 8:
            (OUT / f"w{n:02}.json").write_text(json.dumps({"data": {"metrics": [], "workouts": batch}}))
            n += 1; batch = []
    if batch:
        (OUT / f"w{n:02}.json").write_text(json.dumps({"data": {"metrics": [], "workouts": batch}}))
    (OUT / "metrics.json").write_text(json.dumps({"data": {"metrics": metrics(days), "workouts": []}}))
    (OUT / "sessions.json").write_text(json.dumps([{**s, "start": s["start"].isoformat()} for s in sessions]))
    print(len(workouts), "workouts,", len(sessions), "sessions,", len(days), "days")

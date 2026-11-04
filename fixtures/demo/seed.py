"""Fill a running demo server with a profile, shoes, plans, home-workout sessions and a few notes (all synthetic).

Run from backend/ (for httpx): uv run python ../fixtures/demo/seed.py <out_dir from generate.py>
Env: DEMO_URL (default http://127.0.0.1:8090), DEMO_PASSWORD (default demo-password-1).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from generate import wid  # noqa: E402  the demo workout IDs are deterministic

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out"
c = httpx.Client(base_url=os.environ.get("DEMO_URL", "http://127.0.0.1:8090") + "/api/v1", timeout=60)
c.post("/auth/login", json={"username": "demo", "password": os.environ.get("DEMO_PASSWORD", "demo-password-1")}).raise_for_status()


def ok(r):
    if r.status_code >= 400:
        print(r.request.method, r.request.url, r.status_code, r.text[:400], file=sys.stderr)
        sys.exit(1)
    return r.json() if r.content else None


ok(c.put("/profile", json={"birth_year": None, "sex": None, "hrmax_override": 190, "units": "imperial", "home_tz": "America/New_York"}))

for nm in ("Daily trainer (blue)", "Daily trainer (green)", "Trail shoe"):
    c.post("/shoes", json={"name": nm})
by = {x["name"]: x for x in ok(c.get("/shoes"))["shoes"]}
old, new = by["Daily trainer (blue)"], by["Daily trainer (green)"]
ok(c.put("/shoes/default", json={"shoe_id": old["id"], "from_date": "2026-06-01"}))
ok(c.put("/shoes/default", json={"shoe_id": new["id"], "from_date": "2026-09-14"}))

swing = {"name": "Swing circuit", "format": "amrap", "cap_min": 20, "moves": [
    {"name": "Kettlebell swing", "reps": 15, "weight_kg": 16},
    {"name": "Goblet squat", "reps": 10, "weight_kg": 16},
    {"ladder": "push-up", "rung": 1, "name": "x", "reps": 12},
]}
emom = {"name": "Push & pull EMOM", "format": "emom", "emom_min": 12, "moves": [
    {"ladder": "push-up", "rung": 1, "name": "x", "reps": 10},
    {"ladder": "pull-up", "rung": 0, "name": "x", "reps": 5},
    {"name": "Plank", "seconds": 40},
]}
getup = {"name": "Get-up complex", "format": "complex", "rounds": 5, "moves": [
    {"name": "Turkish get-up", "reps": 2, "weight_kg": 12},
    {"name": "Halo", "reps": 8, "weight_kg": 12},
    {"name": "Suitcase carry", "seconds": 45, "weight_kg": 16},
]}
plans = {k: ok(c.post("/plans", json=p)) for k, p in (("swing", swing), ("push", emom), ("getup", getup))}

sessions = json.loads((OUT / "sessions.json").read_text())
for s in sessions:
    start = datetime.fromisoformat(s["start"]).astimezone(timezone.utc)
    p = plans[s["kind"]]
    plan_in = {k: p[k] for k in ("name", "format", "cap_min", "emom_min", "rounds", "moves", "video_url")}
    ev, t = [], 0
    n = s["n"]
    if p["format"] == "amrap":
        rounds = 4 + min(3, n // 3)
        per_move = [55_000 - 1500 * n, 40_000 - 800 * n, 45_000]
        for r in range(rounds):
            for i, dt in enumerate(per_move):
                t += dt
                ev.append({"t_ms": t, "kind": "next", "move": i, "round": r})
            t += 30_000
            ev.append({"t_ms": t, "kind": "next", "move": 2, "round": r})
        partial = 1
        t = 20 * 60_000
        ev.append({"t_ms": t, "kind": "auto", "move": 1, "round": rounds})
        body = {"rounds_done": rounds, "partial_moves": partial, "fell_short": []}
    else:
        for m in range(12):
            ev.append({"t_ms": (m + 1) * 60_000, "kind": "auto", "move": m % 3, "round": m // 3})
        t = 12 * 60_000
        body = {"rounds_done": 4, "partial_moves": 0, "fell_short": [8, 11] if n < 6 else []}
    ev.append({"t_ms": t, "kind": "end", "move": 0, "round": 0})
    ok(c.post("/sessions", json={"plan_id": p["id"], "plan": plan_in, "weight_kg": 16, "start_utc": start.isoformat(),
                                 "end_utc": (start + timedelta(milliseconds=t)).isoformat(), "events": ev, **body}))

print("plans", {k: v["id"] for k, v in plans.items()}, "sessions", len(sessions))

time.sleep(25)  # let the first recompute land
ok(c.put(f"/workouts/{wid('2026-10-31-long')}/note",
         json={"text": "Felt strong after the hill. Legs heavy the last two miles.", "effort": 7}))
ok(c.put(f"/workouts/{wid('2026-10-11-walk')}/carry", json={"weight_kg": 13}))
ok(c.put("/weeks/2026-W44/note", json={"text": "Good week. Slept well, kept the easy days easy."}))
ok(c.put("/settings/weather", json={"enabled": True}))
print("extras done")

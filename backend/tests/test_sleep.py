"""The night before a run: matching, usual sleep, quality, and through the recompute. All data is invented."""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from helpers import add_run, login, recompute_now
from strydr.pipeline.derive import sleep
from strydr.store import models


def _night(day: date, hours: float, awake=0.3, end_h=6):
    end = datetime(day.year, day.month, day.day, end_h)
    return day.isoformat(), {"totalSleep": hours, "deep": hours * 0.12, "rem": hours * 0.22, "core": hours * 0.66,
                             "awake": awake, "sleepStart": (end - timedelta(hours=hours + awake)).isoformat() + "Z",
                             "sleepEnd": end.isoformat() + "Z"}


NIGHTS = [_night(date(2026, 10, 1) + timedelta(days=i), 7.5) for i in range(20)]


def test_night_before_is_the_last_night_that_ended_before_the_run():
    run = datetime(2026, 10, 15, 8)
    assert sleep.night_before(NIGHTS, run)[0] == "2026-10-15"
    assert sleep.night_before(NIGHTS, datetime(2026, 10, 15, 5)) is None  # that night had not ended; the one before is 23 h old
    assert sleep.night_before(NIGHTS, datetime(2026, 11, 30, 8)) is None  # weeks later: no stand-in night


def test_quality_reads_duration_against_usual_and_time_awake():
    assert sleep.quality(5.5, 0.2, 7.5) == "short"
    assert sleep.quality(5.9, 0.2, None) == "short"
    assert sleep.quality(7.4, 1.5, 7.5) == "restless"
    assert sleep.quality(7.6, 0.3, 7.5) == "good"
    assert sleep.quality(6.6, 0.3, 7.5) == "fair"


def test_before_run_reports_hours_stages_usual_and_morning_readings():
    nights = NIGHTS[:-1] + [_night(date(2026, 10, 20), 5.2, end_h=7)]
    rhr = {(date(2026, 10, 1) + timedelta(days=i)).isoformat(): 55.0 for i in range(19)} | {"2026-10-20": 61.0}
    out = sleep.before_run(nights, datetime(2026, 10, 20, 12), -4 * 3600, rhr, {})
    assert out["night_of"] == "2026-10-20" and out["quality"] == "short"
    assert out["usual_h"] == 7.5 and out["vs_usual_h"] == -2.3
    assert out["wake"] == "03:00" and out["hours_before_run"] == 5.0  # local time from the run's offset
    assert out["rhr_bpm"] == 61.0 and out["rhr_usual_bpm"] == 55.0 and out["hrv_usual_ms"] is None


def test_run_detail_shows_the_night_before(engine, app_client):
    add_run(engine, "r", datetime(2026, 10, 15, 13), 30)
    with Session(engine) as s:
        for d, x in NIGHTS:
            s.add(models.DailyMetric(metric="sleep_analysis", local_date=d, units="hr", value=x["totalSleep"], extra=x,
                                     adapter_version=1, received_at=datetime(2026, 10, 20)))
        s.commit()
    recompute_now(engine, "2026-10-26")
    login(app_client)
    z = app_client.get("/api/v1/workouts/r").json()["sleep"]
    assert z["night_of"] == "2026-10-15" and z["total_h"] == 7.5 and z["quality"] == "good" and z["usual_h"] == 7.5


# ---- story 19: fix a short sleep night ----------------------------------------------------------------------------

from zoneinfo import ZoneInfo

import pytest

UTC = ZoneInfo("UTC")


def _at(start_h: float, total: float, day=date(2026, 10, 20)) -> dict:
    """A night whose sleep starts at `start_h` (UTC) on `day` and records `total` hours."""
    s = datetime(day.year, day.month, day.day) + timedelta(hours=start_h)
    return {"totalSleep": total, "awake": 0.0, "sleepStart": s.isoformat() + "Z", "sleepEnd": (s + timedelta(hours=total)).isoformat() + "Z"}


@pytest.mark.parametrize("start_h,total,usual,flag", [
    (5.17, 1.1, 6.8, True),     # late-worn night
    (23.67 - 24, 4.5, 6.8, False),  # starts 23:40 the day before: not dawn
    (6.0, 2.0, None, True),     # no usual yet: under 3 h
    (6.0, 3.5, None, False),
    (6.0, 3.8, 6.8, True),      # exactly 3 h under
    (6.0, 4.0, 6.8, False),
    (3.9, 1.0, 6.8, False),     # before 04:00
    (11.0, 1.0, 6.8, False),    # 11:00 is outside the window
    (10.9, 1.0, 6.8, True),
])
def test_suspicious(start_h, total, usual, flag):
    x = _at(start_h, total) if start_h >= 0 else _at(24 + start_h, total, date(2026, 10, 19))
    assert sleep.suspicious(x, usual, UTC) is flag


def test_suspicious_uses_home_local_hour_and_skips_corrected():
    x = _at(9.0, 1.0)  # 09:00 UTC is 05:00 in New York (EDT): flagged there, not in UTC+5
    assert sleep.suspicious(x, 7.0, ZoneInfo("America/New_York"))
    assert not sleep.suspicious(x, 7.0, ZoneInfo("Asia/Tashkent"))
    assert not sleep.suspicious({**x, "corrected": True}, 7.0, UTC)


def test_overlay_changes_total_only_and_feeds_the_usual():
    nights = [_night(date(2026, 10, 1) + timedelta(days=i), 7.0) for i in range(9)]
    nights[8] = _night(date(2026, 10, 9), 1.1, end_h=7)
    fixed = sleep.overlay(nights, {"2026-10-09": 6.5})
    assert fixed[8][1]["totalSleep"] == 6.5 and fixed[8][1]["corrected"] is True
    assert fixed[8][1]["deep"] == nights[8][1]["deep"] and fixed[8][1]["awake"] == nights[8][1]["awake"]
    assert nights[8][1]["totalSleep"] == 1.1 and "corrected" not in fixed[0][1]
    assert sleep._usual(fixed + [_night(date(2026, 10, 10), 7.0)], "2026-10-10") == 7.0
    low = [(d, {**x, "totalSleep": 1.1}) for d, x in nights[:5]] + nights[5:]
    assert sleep._usual(sleep.overlay(low, {d: 7.0 for d, _ in low[:5]}) + [_night(date(2026, 10, 10), 7.0)], "2026-10-10") == 7.0


def test_before_run_reports_corrected_and_suspicious():
    nights = [_night(date(2026, 10, 1) + timedelta(days=i), 7.0) for i in range(9)]
    nights.append(("2026-10-10", {**_at(5.0, 1.1, date(2026, 10, 10)), "deep": 0.1, "rem": 0.2, "core": 0.8}))
    run = datetime(2026, 10, 10, 12)
    out = sleep.before_run(nights, run, 0, {}, {}, UTC)
    assert out["total_h"] == 1.1 and out["suspicious"] is True and out["corrected"] is False
    fixed = sleep.before_run(sleep.overlay(nights, {"2026-10-10": 6.5}), run, 0, {}, {}, UTC)
    assert fixed["total_h"] == 6.5 and fixed["corrected"] is True and fixed["suspicious"] is False
    assert fixed["quality"] == "fair" and fixed["vs_usual_h"] == -0.5


def _seed(engine):
    with Session(engine) as s:
        for i, (d, x) in enumerate(NIGHTS[:10]):
            x = dict(x)
            if d == "2026-10-10":
                x = _at(5.2, 1.1, date(2026, 10, 10)) | {"awake": 0.2}
            s.add(models.DailyMetric(metric="sleep_analysis", local_date=d, units="hr", value=x["totalSleep"], extra=x,
                                     adapter_version=1, received_at=datetime(2026, 10, 20)))
        s.commit()


def test_correction_api_roundtrip_and_survives_recompute(engine, app_client):
    add_run(engine, "r", datetime(2026, 10, 10, 13), 30)
    _seed(engine)
    recompute_now(engine, "2026-10-26")
    login(app_client)
    url = "/api/v1/sleep/2026-10-10/correction"
    z = app_client.get("/api/v1/workouts/r").json()["sleep"]
    assert z["total_h"] == 1.1 and z["suspicious"] is True and z["corrected"] is False
    r = app_client.put(url, json={"hours": 6.5})
    assert r.status_code == 200 and r.json() == {"local_date": "2026-10-10", "hours": 6.5}
    with Session(engine) as s:
        pending = s.query(models.Job).filter(models.Job.type == "recompute", models.Job.status == "pending").count()
    assert pending >= 1
    recompute_now(engine, "2026-10-26")
    recompute_now(engine, "2026-10-26")  # a full recompute again: the correction persists
    z = app_client.get("/api/v1/workouts/r").json()["sleep"]
    assert z["total_h"] == 6.5 and z["corrected"] is True and z["suspicious"] is False
    assert app_client.delete(url).json() == {"local_date": "2026-10-10", "hours": None}
    recompute_now(engine, "2026-10-26")
    z = app_client.get("/api/v1/workouts/r").json()["sleep"]
    assert z["total_h"] == 1.1 and z["corrected"] is False and z["suspicious"] is True


@pytest.mark.parametrize("hours", [0, 0.4, 20, 14.1, "abc", None])
def test_correction_rejects_bad_hours(engine, app_client, hours):
    _seed(engine)
    login(app_client)
    assert app_client.put("/api/v1/sleep/2026-10-10/correction", json={"hours": hours}).status_code == 422


def test_correction_edges(engine, app_client):
    _seed(engine)
    login(app_client)
    base = "/api/v1/sleep/{}/correction"
    assert app_client.put(base.format("2026-10-10"), json={"hours": 0.5}).status_code == 200
    assert app_client.put(base.format("2026-10-10"), json={"hours": 14}).status_code == 200
    assert app_client.put(base.format("2026-12-01"), json={"hours": 6}).status_code == 404
    assert app_client.put(base.format("nope"), json={"hours": 6}).status_code == 422
    assert app_client.delete(base.format("2026-10-09")).status_code == 200  # nothing to clear is harmless


def test_correction_survives_reparse_rewriting_the_row(engine):
    # reparse rewrites the daily_metric row; the correction lives in its own table, so the overlay still applies
    _seed(engine)
    with Session(engine) as s:
        s.add(models.SleepCorrection(local_date="2026-10-10", hours=6.5, updated_at=datetime(2026, 11, 3)))
        s.query(models.DailyMetric).filter_by(metric="sleep_analysis", local_date="2026-10-10").delete()
        x = _at(5.2, 1.1, date(2026, 10, 10))
        s.add(models.DailyMetric(metric="sleep_analysis", local_date="2026-10-10", units="hr", value=1.1, extra=x,
                                 adapter_version=2, received_at=datetime(2026, 11, 3)))
        s.commit()
    add_run(engine, "r", datetime(2026, 10, 10, 13), 30)
    recompute_now(engine, "2026-10-26")
    with Session(engine) as s:
        det = s.query(models.WorkoutDetail).filter_by(workout_id="r").one()
        assert det.sleep["total_h"] == 6.5 and det.sleep["corrected"] is True


def test_corrected_night_has_no_stage_ratios():
    nights = [_night(date(2026, 10, 1) + timedelta(days=i), 7.0) for i in range(9)]
    nights.append(_night(date(2026, 10, 10), 1.1, end_h=7))
    run = datetime(2026, 10, 10, 12)
    assert sleep.before_run(nights, run, 0, {}, {})["efficiency_pct"] is not None
    out = sleep.before_run(sleep.overlay(nights, {"2026-10-10": 6.5}), run, 0, {}, {})
    assert out["efficiency_pct"] is None and out["deep_rem_pct"] is None


def test_orphan_correction_can_be_cleared(engine, app_client):
    login(app_client)
    with Session(engine) as s:
        s.add(models.SleepCorrection(local_date="2026-09-01", hours=6.0, updated_at=datetime(2026, 11, 3)))
        s.commit()
    r = app_client.delete("/api/v1/sleep/2026-09-01/correction")
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.get(models.SleepCorrection, "2026-09-01") is None
    assert app_client.delete("/api/v1/sleep/nope/correction").status_code == 422

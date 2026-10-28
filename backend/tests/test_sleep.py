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

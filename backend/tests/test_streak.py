from datetime import date, datetime

import pytest

from strydr import progress
from strydr.jobs import queue

from helpers import add_run, login
from test_sessions import session

API = "/api/v1"
TODAY = date(2026, 11, 4)  # a Wednesday; this week starts Monday 2026-11-02


def mon(n):  # the Monday n weeks before this week
    return date(2026, 11, 2).fromordinal(date(2026, 11, 2).toordinal() - 7 * n)


# --- the pure helper ---------------------------------------------------------

def test_running_streak_includes_this_week():
    r = progress.streak([mon(0), mon(1), mon(2), mon(3)], TODAY)
    assert (r.weeks, r.this_week, r.last_streak) == (4, True, 4)


def test_open_week_never_breaks_the_streak():
    r = progress.streak([mon(1), mon(2), mon(3)], TODAY)
    assert (r.weeks, r.this_week, r.last_streak) == (3, False, 3)


def test_broken_streak_reports_the_last_run():
    r = progress.streak([mon(i) for i in range(2, 7)], TODAY)
    assert (r.weeks, r.this_week, r.last_streak) == (0, False, 5)


def test_nothing_ever():
    r = progress.streak([], TODAY)
    assert (r.weeks, r.this_week, r.last_streak) == (0, False, 0)
    assert len(r.recent) == 8 and not any(c for _, c in r.recent)
    assert r.recent[-1][0] == mon(0) and r.recent[0][0] == mon(7)


def test_several_days_in_a_week_count_once_and_sunday_belongs_to_its_week():
    r = progress.streak([date(2026, 11, 1), date(2026, 10, 27), date(2026, 10, 26)], TODAY)  # Sun, Tue, Mon of last week
    assert r.weeks == 1 and r.recent[-2] == (mon(1), True)


def test_streak_runs_across_a_year_boundary():
    r = progress.streak([date(2025, 12, 29), date(2026, 1, 5), date(2026, 1, 12)], date(2026, 1, 14))
    assert (r.weeks, r.this_week, r.last_streak) == (3, True, 3)


def test_streak_longer_than_the_eight_shown_weeks():
    r = progress.streak([mon(i) for i in range(12)], TODAY)
    assert r.weeks == 12 and len(r.recent) == 8 and all(c for _, c in r.recent)


# --- the route ---------------------------------------------------------------

@pytest.fixture
def c(app_client, monkeypatch):
    monkeypatch.setattr(queue, "local_today", lambda tz: "2026-11-04")
    login(app_client)
    return app_client


def test_requires_auth(app_client):
    assert app_client.get(f"{API}/streak").status_code == 401


def test_empty_db(c):
    r = c.get(f"{API}/streak").json()
    assert (r["weeks"], r["this_week"], r["last_streak"]) == (0, False, 0)
    assert len(r["recent"]) == 8 and all(not w["counted"] for w in r["recent"])
    assert r["recent"][-1]["week_start"] == "2026-11-02"


def test_sessions_in_four_weeks(c):
    for i, day in enumerate(["2026-11-03", "2026-10-27", "2026-10-20", "2026-10-13"]):
        c.post(f"{API}/sessions", json=session(start_utc=f"{day}T18:00:00Z", end_utc=f"{day}T18:05:00Z", rounds_done=1, partial_moves=0))
    r = c.get(f"{API}/streak").json()
    assert (r["weeks"], r["this_week"]) == (4, True)
    assert [w["counted"] for w in r["recent"]] == [False] * 4 + [True] * 4


def _workout(engine, wid, start, type_, indoor):
    add_run(engine, wid, start, 20, type_=type_, route=not indoor)


def test_watch_strength_and_indoor_walk_count_outdoor_does_not(c, engine):
    _workout(engine, "s1", datetime(2026, 11, 3, 18), "strength", True)
    _workout(engine, "w1", datetime(2026, 10, 27, 18), "walk", True)
    _workout(engine, "w2", datetime(2026, 10, 20, 18), "walk", False)
    _workout(engine, "r1", datetime(2026, 10, 20, 19), "run", False)
    _workout(engine, "h1", datetime(2026, 10, 13, 19), "hike", False)
    r = c.get(f"{API}/streak").json()
    assert (r["weeks"], r["this_week"], r["last_streak"]) == (2, True, 2)
    assert [w["counted"] for w in r["recent"]][-4:] == [False, False, True, True]


def test_session_and_its_watch_workout_count_once(c, engine):
    c.post(f"{API}/sessions", json=session(start_utc="2026-11-03T18:00:00Z", end_utc="2026-11-03T18:10:00Z"))
    _workout(engine, "s1", datetime(2026, 11, 3, 18), "strength", True)
    assert c.get(f"{API}/streak").json()["weeks"] == 1


def test_sunday_night_in_new_york_counts_for_that_sunday(c):
    # 2026-11-02 04:30 UTC is Sunday 23:30 in New York: last week, not this one
    body = {"units": "metric", "home_tz": "America/New_York"}
    assert c.put(f"{API}/profile", json=body).status_code == 200
    c.post(f"{API}/sessions", json=session(start_utc="2026-11-02T04:30:00Z", end_utc="2026-11-02T04:40:00Z"))
    r = c.get(f"{API}/streak").json()
    assert r["this_week"] is False and r["recent"][-2]["counted"] is True and r["weeks"] == 1

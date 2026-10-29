from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.store import generations, models, settings

from helpers import add_run, login, recompute_now

AS_OF = date(2026, 10, 26)


def _hr_runs(engine, n=5):
    for i in range(n):
        hrs = [140.0] * 30
        hrs[10], hrs[11] = 168.0, 172.0  # a hard stretch: HRmax ignores it
        add_run(engine, f"hr{i}", datetime(2026, 10, 1 + i), 30, 3.0, hr=hrs)


def _profile(engine, **cfg):
    with Session(engine) as s:
        settings.write(s, settings.UserSettings(**cfg))
        s.commit()
    recompute_now(engine, AS_OF.isoformat())
    with Session(engine) as s:
        return s.execute(generations.scoped(models.ProfileResult)).scalar_one()


def test_tanaka_when_no_runs(engine):
    p = _profile(engine, birth_year=1990)
    assert (p.hrmax, p.hrmax_source) == (183, "tanaka")  # 208 - 0.7 * 36
    assert p.zone_bounds_bpm == [109.8, 128.1, 146.4, 164.7]
    assert p.easy_ceiling_bpm == 146.4  # 80% of HRmax


def test_no_birth_year_means_unavailable(engine):
    p = _profile(engine)
    assert (p.hrmax, p.hrmax_source, p.zone_bounds_bpm, p.easy_ceiling_bpm) == (None, "unavailable", None, None)


def test_age_only_gives_tanaka_even_with_hard_runs(engine):
    _hr_runs(engine)
    p = _profile(engine, birth_year=1990)
    assert (p.hrmax, p.hrmax_source) == (183, "tanaka")  # the 172 bpm stretch is never the maximum


def test_override_beats_age(engine):
    _hr_runs(engine)
    p = _profile(engine, birth_year=1990, hrmax_override=190)
    assert (p.hrmax, p.hrmax_source) == (190, "override")


def test_hr_runs_without_birth_year_are_unavailable(engine):
    _hr_runs(engine)
    p = _profile(engine)
    assert (p.hrmax, p.hrmax_source) == (None, "unavailable")


def test_resting_hr_and_hrv_baselines(engine):
    with Session(engine) as s:
        for i in range(30):
            d = (AS_OF - timedelta(days=i)).isoformat()
            s.add(models.DailyMetric(metric="resting_heart_rate", local_date=d, units="count/min",
                                     value=0.0 if i == 3 else 50.0 + (i < 7) * 4, adapter_version=1, received_at=datetime(2026, 10, 1)))
        for i in range(60):
            s.add(models.DailyMetric(metric="heart_rate_variability", local_date=(AS_OF - timedelta(days=i)).isoformat(),
                                     units="ms", value=60.0, adapter_version=1, received_at=datetime(2026, 10, 1)))
        s.commit()
    p = _profile(engine)
    assert p.rhr_7d_median == 54.0 and p.rhr_30d_baseline == 50.0 and p.hrv_60d_baseline == 60.0


def test_settings_write_enqueues_recompute_in_same_transaction(engine, app_client, worker):
    login(app_client)
    body = {"birth_year": 1990, "sex": "female", "hrmax_override": None, "zones": None, "units": "imperial",
            "home_tz": "America/New_York"}
    r = app_client.put("/api/v1/profile", json=body)
    assert r.status_code == 200 and r.json()["recompute_pending"] is True and r.json()["resolved"] is None
    worker.run_all()
    got = app_client.get("/api/v1/profile").json()
    assert got["settings"] == body and got["recompute_pending"] is False
    assert got["resolved"]["hrmax_source"] == "tanaka" and got["resolved"]["hrmax"] == 183
    assert got["zone_bounds_pct"] == [60, 70, 80, 90]


def test_profile_validation(app_client):
    login(app_client)
    base = {"units": "metric", "home_tz": "UTC"}
    assert app_client.put("/api/v1/profile", json={**base, "home_tz": "Mars/Base"}).status_code == 422
    assert app_client.put("/api/v1/profile", json={**base, "zones": [70, 60, 80, 90]}).status_code == 422
    assert app_client.put("/api/v1/profile", json={**base, "hrmax_override": 50}).status_code == 422
    assert app_client.put("/api/v1/profile", json={**base, "sex": "x"}).status_code == 422

"""Opt-in weather (AD-10 weather exception): the request shape, the fetch job and the switch. No real network."""
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from helpers import ORIGIN, add_run, login, recompute_now
from strydr.egress import EgressError
from strydr.egress.weather import HOURLY, WEATHER_HOST, OpenMeteo, WeatherRequest, cell_of
from strydr.jobs import Worker
from strydr.jobs import weather as weather_job
from strydr.store import models, settings


def _reply(day: str, temp=18.0):
    times = [f"{day}T{h:02d}:00" for h in range(24)]
    body = {"time": times} | {k: [temp if k == "temperature_2m" else 5.0] * 24 for k in HOURLY}
    return {"latitude": 0, "longitude": 0, "hourly": body}


class Fake:
    def __init__(self, status=200, temp=18.0):
        self.requests: list[httpx.Request] = []
        self.status, self.temp = status, temp

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        day = parse_qs(request.url.query.decode())["start_date"][0]
        return httpx.Response(self.status, json=_reply(day, self.temp))

    def client(self) -> OpenMeteo:
        return OpenMeteo(transport=httpx.MockTransport(self.handler))


def test_requests_take_only_a_coarse_cell_and_a_date():
    assert cell_of(52.3712, 4.8961) == (52.4, 4.9)
    assert WeatherRequest(lat=52.4, lon=4.9, utc_date="2026-10-03").cell == "52.4,4.9"
    with pytest.raises(ValidationError):
        WeatherRequest(lat=52.3712, lon=4.9, utc_date="2026-10-03")  # finer than the grid
    with pytest.raises(ValidationError):
        WeatherRequest(lat=52.4, lon=4.9, utc_date="2026-10-03", start="07:00")  # nothing else may ride along
    with pytest.raises(TypeError):
        OpenMeteo(transport=httpx.MockTransport(lambda r: httpx.Response(200))).hourly({"lat": 52.4})


def test_the_request_carries_no_time_of_day_track_or_key():
    fake = Fake()
    fake.client().hourly(WeatherRequest(lat=52.4, lon=4.9, utc_date="2026-10-03"))
    req = fake.requests[0]
    q = parse_qs(req.url.query.decode())
    assert req.url.host == WEATHER_HOST and req.method == "GET"
    assert set(q) == {"latitude", "longitude", "start_date", "end_date", "hourly", "wind_speed_unit", "timezone"}
    assert q["latitude"] == ["52.4"] and q["start_date"] == q["end_date"] == ["2026-10-03"]
    assert "authorization" not in {k.lower() for k in req.headers}


def test_a_provider_error_is_an_egress_error():
    fake = Fake(status=500)
    with pytest.raises(EgressError):
        fake.client().hourly(WeatherRequest(lat=52.4, lon=4.9, utc_date="2026-10-03"))


def _seed(engine, enabled=True, zone=False):
    add_run(engine, "a", datetime(2026, 10, 3, 7), 30)
    add_run(engine, "b", datetime(2026, 10, 3, 18), 20)  # same day and cell: served from the cache
    add_run(engine, "indoor", datetime(2026, 10, 4, 7), 20, route=False)
    with Session(engine) as s:
        settings.write_weather_enabled(s, enabled)
        if zone:  # covers the whole synthetic track
            s.add(models.PrivacyZone(lat=ORIGIN[0], lon=ORIGIN[1], radius_m=20000, offset_north_m=0, offset_east_m=0, trim_m=100))
        s.commit()
    recompute_now(engine, "2026-10-26")


def test_fetch_fills_outdoor_runs_with_one_request_per_cell_and_day(engine):
    _seed(engine)
    fake = Fake()
    assert weather_job.fetch(engine, fake.client()) == 2
    assert len(fake.requests) == 1
    with Session(engine) as s:
        rows = {r.workout_id: r for r in s.execute(select(models.WorkoutWeather)).scalars()}
    assert set(rows) == {"a", "b"} and rows["a"].status == "ok" and rows["a"].temp_c == 18.0
    assert weather_job.fetch(engine, fake.client()) == 0 and len(fake.requests) == 1  # nothing left to do
    recompute_now(engine, "2026-10-26")
    with Session(engine) as s:
        detail = s.execute(select(models.WorkoutDetail).where(models.WorkoutDetail.workout_id == "a")
                           .order_by(models.WorkoutDetail.generation_id.desc())).scalars().first()
    assert detail.conditions["temp_c"] == 18.0 and detail.conditions["sources"]["temperature"] == "open-meteo"


def test_nothing_is_sent_while_weather_is_off(engine):
    _seed(engine, enabled=False)
    fake = Fake()
    assert weather_job.fetch(engine, fake.client()) == 0 and fake.requests == []


def test_a_run_inside_a_privacy_zone_is_skipped_without_a_request(engine):
    _seed(engine, zone=True)
    fake = Fake()
    assert weather_job.fetch(engine, fake.client()) == 0 and fake.requests == []
    with Session(engine) as s:
        assert {r.status for r in s.execute(select(models.WorkoutWeather)).scalars()} == {"skipped"}


def test_an_outage_marks_the_run_unavailable_and_stops(engine):
    _seed(engine)
    fake = Fake(status=503)
    assert weather_job.fetch(engine, fake.client()) == 0 and len(fake.requests) == 1
    with Session(engine) as s:
        assert [r.status for r in s.execute(select(models.WorkoutWeather)).scalars()] == ["unavailable"]


def test_the_switch_enqueues_a_fetch_and_off_forgets_everything(engine, app_client):
    _seed(engine, enabled=False)
    login(app_client)
    assert app_client.get("/api/v1/settings/weather").json()["enabled"] is False
    r = app_client.put("/api/v1/settings/weather", json={"enabled": True})
    assert r.status_code == 200 and r.json()["enabled"] and r.json()["provider_host"] == WEATHER_HOST
    fake = Fake()
    Worker(engine, "UTC", backoff_s=0, weather_client=fake.client()).run_all()
    assert app_client.get("/api/v1/settings/weather").json()["fetched"] == 2
    assert app_client.get("/api/v1/workouts/a").json()["conditions"]["temp_c"] == 18.0
    app_client.put("/api/v1/settings/weather", json={"enabled": False})
    with Session(engine) as s:
        assert s.execute(select(models.WorkoutWeather)).first() is None and s.execute(select(models.WeatherCache)).first() is None

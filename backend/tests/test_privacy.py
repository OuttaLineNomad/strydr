import math
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from strydr.api import create_app
from strydr.api.schemas import DisplayGeometry
from strydr.pipeline.derive.routes.display import for_display
from strydr.store import models
from strydr.store.zones import TRIM_M, create_zone

from helpers import ORIGIN, add_run, login, recompute_now

COORD_NAMES = {"lat", "lon", "lng", "latitude", "longitude", "coordinates", "route", "geometry", "points"}


def _metres(p, centre):
    return math.hypot((p[0] - centre[0]) * 111_320, (p[1] - centre[1]) * 111_320 * math.cos(math.radians(centre[0])))


def _track(n=1800, step_m=3.0):
    return {"lat": [ORIGIN[0] + i * step_m / 111_320 for i in range(n)], "lon": [ORIGIN[1]] * n}


def test_zone_offset_is_drawn_once_and_keeps_home_inside_the_clip(engine):
    with Session(engine) as s:
        zones = [create_zone(s, *ORIGIN) for _ in range(50)]
        s.commit()
        assert all(math.hypot(z.offset_north_m, z.offset_east_m) <= z.trim_m == TRIM_M for z in zones)
        assert len({(z.offset_north_m, z.offset_east_m) for z in zones}) > 1
        z = s.get(models.PrivacyZone, zones[0].id)
        assert (z.offset_north_m, z.offset_east_m) == (zones[0].offset_north_m, zones[0].offset_east_m)


def test_for_display_clips_every_point_inside_the_zone():
    zone = models.PrivacyZone(lat=ORIGIN[0], lon=ORIGIN[1], radius_m=400, offset_north_m=60, offset_east_m=-40, trim_m=100)
    geo = for_display(_track(), [zone])
    pts = [p for seg in geo["segments"] for p in seg]
    assert pts and all(_metres(p, ORIGIN) > 400 for p in pts)  # nothing within the true radius
    assert _metres(geo["start"], ORIGIN) > 400  # markers come from the clipped track only
    assert geo["bounds"][0] == min(p[0] for p in pts) and geo["start"] == geo["segments"][0][0]


def test_for_display_splits_the_track_around_a_zone_in_the_middle():
    mid = (ORIGIN[0] + 2000 / 111_320, ORIGIN[1])
    zone = models.PrivacyZone(lat=mid[0], lon=mid[1], radius_m=300, offset_north_m=0, offset_east_m=0, trim_m=100)
    geo = for_display(_track(n=1500, step_m=3.0), [zone])
    assert len(geo["segments"]) == 2 and all(_metres(p, mid) > 400 for seg in geo["segments"] for p in seg)


def test_without_zones_and_fully_hidden_tracks():
    assert for_display(_track(), [])["start"][0] == pytest.approx(ORIGIN[0], abs=1e-4)
    zone = models.PrivacyZone(lat=ORIGIN[0], lon=ORIGIN[1], radius_m=10000, offset_north_m=0, offset_east_m=0, trim_m=100)
    assert for_display(_track(), [zone]) is None


def test_api_serves_only_clipped_geometry(engine, app_client):
    with Session(engine) as s:
        create_zone(s, *ORIGIN)
        s.commit()
    add_run(engine, "home-run", datetime(2026, 10, 20, 7), 30, 3.0)  # starts at the zone centre
    recompute_now(engine, "2026-10-26")
    login(app_client)
    geo = app_client.get("/api/v1/workouts/home-run").json()["display_geometry"]
    pts = [p for seg in geo["segments"] for p in seg]
    assert pts and all(_metres(p, ORIGIN) > 400 for p in pts) and _metres(geo["start"], ORIGIN) > 400
    assert "display_geometry" not in app_client.get("/api/v1/workouts").text


def _walk(schema, path=()):
    if isinstance(schema, dict):
        for k, v in schema.items():
            yield from _walk(v, path + (k,))
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            yield from _walk(v, path + (i,))
    else:
        yield path, schema


def test_openapi_exposes_raw_coordinates_only_through_display_geometry():
    spec = create_app(None).openapi()
    schemas = spec["components"]["schemas"]
    assert "DisplayGeometry" in schemas
    for name, schema in schemas.items():
        if name == "PrivacyZoneIn":  # the one request model that takes a centre; no endpoint returns it
            continue
        for prop, body in schema.get("properties", {}).items():
            assert prop.lower() not in COORD_NAMES or (name, prop) == ("WorkoutDetailOut", "display_geometry"), (name, prop)
            if name != "DisplayGeometry":
                # a coordinate pair or a list of them is a nested numeric array
                items = body.get("items", {}) if body.get("type") == "array" else {}
                assert not (items.get("type") == "array" or "prefixItems" in items or "prefixItems" in body), (name, prop)
    refs = [p for p, v in _walk(spec["paths"]) if v == "#/components/schemas/DisplayGeometry"]
    assert refs == []  # reachable only through WorkoutDetailOut, never referenced from a path directly
    users = [n for n, s in schemas.items() if "#/components/schemas/DisplayGeometry" in str(s)]
    assert sorted(users) == ["RouteDetailOut", "RouteMapLine", "RouteOut", "WorkoutDetailOut"]  # map: one line per workout
    assert {"lat", "lon"}.isdisjoint(schemas["PrivacyZoneOut"]["properties"])
    assert DisplayGeometry.model_fields.keys() == {"segments", "start", "end", "bounds", "walk_segments"}

"""Opt-in historical weather (AD-10 weather exception): the only shape that may ask the weather provider.

A request carries a 0.1 degree grid cell (about 11 km) and a UTC date, nothing else: no start time, no track,
no zones, no identity, no key. The reply is hourly values for that cell and day; it never holds coordinates
of the runner. Open-Meteo's archive serves ERA5 reanalysis blended with ECMWF IFS (no delay for recent days),
free for non-commercial use under CC BY 4.0 (attribution shown in Settings).
"""
import logging
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from strydr.egress.providers import TIMEOUT_S, EgressError

log = logging.getLogger("strydr.egress")

WEATHER_HOST = "archive-api.open-meteo.com"
WEATHER_URL = f"https://{WEATHER_HOST}/v1/archive"
HOURLY = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature", "precipitation",
          "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "cloud_cover")
GRID_DEG = 0.1


def cell_of(lat: float, lon: float) -> tuple[float, float]:
    """The grid cell a point falls in: what is sent instead of the point."""
    return round(round(lat / GRID_DEG) * GRID_DEG, 1), round(round(lon / GRID_DEG) * GRID_DEG, 1)


class WeatherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    utc_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("lat", "lon")
    @classmethod
    def _coarse(cls, v: float) -> float:
        if round(v, 1) != v:  # a finer coordinate must never leave the server
            raise ValueError("weather requests take a 0.1 degree grid cell only")
        return v

    @property
    def cell(self) -> str:
        return f"{self.lat:.1f},{self.lon:.1f}"


_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


class OpenMeteo:
    """GET the archive endpoint. `transport` lets tests supply an in-process fake (no network)."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def hourly(self, req: WeatherRequest) -> dict[str, list]:
        if not isinstance(req, WeatherRequest):  # AD-10: nothing but a WeatherRequest reaches the provider
            raise TypeError("weather egress accepts only a WeatherRequest")
        params = {"latitude": f"{req.lat:.1f}", "longitude": f"{req.lon:.1f}", "start_date": req.utc_date,
                  "end_date": req.utc_date, "hourly": ",".join(HOURLY), "wind_speed_unit": "ms", "timezone": "GMT"}
        try:
            with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S), transport=self._transport, follow_redirects=False) as c:
                r = c.get(WEATHER_URL, params=params, headers={"User-Agent": "strydr"})
                r.raise_for_status()
                h = r.json()["hourly"]
            times = [str(t) for t in h["time"]]
            if not all(_TIME.match(t) for t in times):
                raise ValueError("unexpected time format")
            out: dict[str, list] = {"time": times}
            for k in HOURLY:
                vals = h.get(k) or [None] * len(times)
                out[k] = [float(v) if isinstance(v, (int, float)) else None for v in vals][:len(times)]
            return out
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise EgressError(type(e).__name__) from None

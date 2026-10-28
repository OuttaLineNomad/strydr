"""Run conditions (weather) and the heat adjustment to pace. Pure: no DB, clock or I/O.

Apple's own reading (temperature and humidity at the start of an outdoor workout) wins where it exists; the
optional fetched weather (`workout_weather`, opt-in) fills gaps and adds wind, rain, cloud and feels-like.

The heat adjustment is the temperature + dew point rule of thumb (both in degF, summed), popularised by
Hadley's chart: no adjustment up to 100, rising to about 10% at 180. It is coaching folklore with modest
evidence, so the UI and templates call it an estimate.
"""
import math
from collections.abc import Mapping

# (temp + dew point in degF, % slower) breakpoints; linear in between, capped at the last one.
HEAT_CURVE = ((100.0, 0.0), (110.0, 0.5), (120.0, 1.0), (130.0, 2.0), (140.0, 3.0), (150.0, 4.5),
              (160.0, 6.0), (170.0, 8.0), (180.0, 10.0))
WINDY_MPS = 6.0  # about 13 mph at 10 m: noticeable on a run
RAIN_MM_H = 0.2


def f_of(c: float) -> float:
    return c * 9 / 5 + 32


def dew_point_c(temp_c: float, rh_pct: float) -> float | None:
    """Magnus formula (Alduchov and Eskridge constants); good to about 0.4 degC over -40..50 degC."""
    if rh_pct is None or rh_pct <= 0 or rh_pct > 100:
        return None
    a, b = 17.625, 243.04
    g = math.log(rh_pct / 100) + a * temp_c / (b + temp_c)
    return b * g / (a - g)


def heat_adjust_pct(sum_f: float) -> float:
    if sum_f <= HEAT_CURVE[0][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(HEAT_CURVE, HEAT_CURVE[1:]):
        if sum_f <= x1:
            return y0 + (y1 - y0) * (sum_f - x0) / (x1 - x0)
    return HEAT_CURVE[-1][1]


def band(temp_c: float, sum_f: float | None) -> str:
    """One closed word for the conditions (also an AI term)."""
    if temp_c < 0:
        return "freezing"
    if temp_c < 8:
        return "cold"
    if sum_f is None:  # no humidity: temperature alone, never "ideal" for a hot run
        return "hot" if temp_c >= 27 else "warm" if temp_c >= 21 else "ideal"
    if sum_f <= 100:
        return "ideal"
    if sum_f <= 130:
        return "warm"
    if sum_f <= 150:
        return "hot"
    return "oppressive"


def conditions(temp_c: float | None, humidity_pct: float | None, fetched: Mapping | None,
               avg_speed_mps: float | None) -> dict | None:
    """The run's conditions, or None when nothing is known. `fetched` is a `workout_weather` row as a dict."""
    fetched = fetched or {}
    sources = {}
    t, rh = temp_c, humidity_pct
    if t is not None:
        sources["temperature"] = "apple"
    elif fetched.get("temp_c") is not None:
        t, sources["temperature"] = fetched["temp_c"], "open-meteo"
    if rh is not None:
        sources["humidity"] = "apple"
    elif fetched.get("humidity_pct") is not None:
        rh, sources["humidity"] = fetched["humidity_pct"], "open-meteo"
    if t is None:
        return None
    # Relative humidity only means something against the temperature it was measured with: Apple's pair, or the
    # provider's own dew point. Never Apple's temperature with the grid's humidity.
    if sources.get("humidity") == "apple" and sources.get("temperature") == "apple":
        dew = dew_point_c(t, rh)
    elif fetched.get("dew_point_c") is not None:
        dew, sources["dew_point"] = fetched["dew_point_c"], "open-meteo"
    else:
        dew = dew_point_c(t, rh) if rh is not None else None
    sum_f = f_of(t) + f_of(dew) if dew is not None else None
    adj = heat_adjust_pct(sum_f) if sum_f is not None else None
    wind, rain = fetched.get("wind_ms"), fetched.get("precip_mm_h")
    return {
        "temp_c": round(t, 1),
        "humidity_pct": round(rh) if rh is not None else None,
        "dew_point_c": round(dew, 1) if dew is not None else None,
        "apparent_c": fetched.get("apparent_c"),
        "wind_ms": wind, "wind_dir_deg": fetched.get("wind_dir_deg"), "gust_ms": fetched.get("gust_ms"),
        "precip_mm_h": rain, "cloud_pct": fetched.get("cloud_pct"),
        "temp_dew_sum_f": round(sum_f) if sum_f is not None else None,
        "heat_adjust_pct": round(adj, 2) if adj is not None else None,
        "heat_adjusted_speed_mps": round(avg_speed_mps * (1 + adj / 100), 4) if adj and avg_speed_mps else None,
        "band": band(t, sum_f),
        "windy": wind is not None and wind >= WINDY_MPS,
        "rain": rain is not None and rain >= RAIN_MM_H,
        "sources": sources | ({"wind": "open-meteo"} if wind is not None else {}),
    }

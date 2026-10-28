"""Unit normalisation. HAE units are mixed per field, so every value is converted by its own `units`."""

# unit -> (canonical unit, multiplier)
_LINEAR = {
    "m": ("m", 1.0), "km": ("m", 1000.0), "mi": ("m", 1609.344), "ft": ("m", 0.3048), "in": ("m", 0.0254),
    "cm": ("cm", 1.0),
    "m/s": ("m/s", 1.0), "km/hr": ("m/s", 1 / 3.6), "mi/hr": ("m/s", 0.44704), "ft/s": ("m/s", 0.3048),
    "lb": ("kg", 0.45359237), "kg": ("kg", 1.0),
}


def to_c(v: float) -> float:
    return (v - 32.0) * 5.0 / 9.0


def convert(value: float, units: str) -> tuple[float, str] | None:
    """Return (value, canonical_units), or None when the unit is not a known convertible one."""
    if units in ("degF", "°F"):
        return to_c(value), "degC"
    if units in ("degC", "°C"):
        return value, "degC"
    hit = _LINEAR.get(units)
    if hit is None:
        return None
    return value * hit[1], hit[0]


def passthrough(value: float, units: str) -> tuple[float, str]:
    """Convert when the unit is known; otherwise keep value and unit as given (unit-neutral fields)."""
    return convert(value, units) or (value, units)

"""Privacy-zone creation (AD-10): the randomized centre offset and trim are drawn once and stored."""
import math
import secrets

from sqlalchemy.orm import Session

from strydr.store import models

DEFAULT_RADIUS_M = 400.0  # FR-23b
TRIM_M = 100.0


def create_zone(s: Session, lat: float, lon: float, radius_m: float = DEFAULT_RADIUS_M) -> models.PrivacyZone:
    rng = secrets.SystemRandom()
    distance = TRIM_M * math.sqrt(rng.random())  # never beyond trim_m, so the true circle stays inside the clip circle
    bearing = rng.uniform(0, 2 * math.pi)
    zone = models.PrivacyZone(
        lat=lat, lon=lon, radius_m=radius_m,
        offset_north_m=distance * math.cos(bearing), offset_east_m=distance * math.sin(bearing), trim_m=TRIM_M,
    )
    s.add(zone)
    return zone

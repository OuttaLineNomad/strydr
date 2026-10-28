"""Privacy zones (FR-23b, AD-10).

The centre and radius are accepted over the private app port and stored, with the randomized offset and trim drawn once
(store.zones). No endpoint returns the centre or the offset: the API echoes only an id and the radius, so a stolen
session or a cached response cannot reveal where home is. The map is clipped by the recompute (derive/routes), and only
the clipped geometry is ever served.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.store import models
from strydr.store.zones import create_zone


def router(api: Api) -> APIRouter:
    r = APIRouter(prefix="/privacy-zones", tags=["privacy"], dependencies=api.auth)

    @r.get("", response_model=list[sc.PrivacyZoneOut])
    def list_zones() -> list[sc.PrivacyZoneOut]:
        with Session(api.engine) as s:
            return [sc.PrivacyZoneOut(id=z.id, radius_m=z.radius_m)
                    for z in s.execute(select(models.PrivacyZone).order_by(models.PrivacyZone.id)).scalars()]

    @r.post("", response_model=sc.PrivacyZoneOut, status_code=201)
    def add_zone(body: sc.PrivacyZoneIn) -> sc.PrivacyZoneOut:
        with Session(api.engine) as s:
            zone = create_zone(s, body.lat, body.lon, body.radius_m)
            api.enqueue_recompute(s)  # AD-1: privacy_zone is a pipeline input; the write and its job commit together
            s.commit()
            out = sc.PrivacyZoneOut(id=zone.id, radius_m=zone.radius_m)
        api.wake()
        return out

    @r.delete("/{zone_id}", status_code=204)
    def delete_zone(zone_id: int) -> None:
        with Session(api.engine) as s:
            zone = s.get(models.PrivacyZone, zone_id)
            if zone is None:
                raise HTTPException(status_code=404, detail="zone not found")
            s.delete(zone)
            api.enqueue_recompute(s)
            s.commit()
        api.wake()

    return r

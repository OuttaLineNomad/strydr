"""Shoes: the list with totals, the default-shoe history, and the per-run choice. User tables only; shoes are not a
pipeline input, so no write here enqueues a recompute."""
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from strydr import shoes
from strydr.api import schemas as sc
from strydr.api.common import Api
from strydr.jobs import queue
from strydr.store import models, settings
from strydr.store.util import utcnow


def result_for(s: Session, workout_id: str) -> sc.WorkoutShoeResult:
    return sc.WorkoutShoeResult(shoe=shoe_out_for(s, workout_id), chosen=s.get(models.WorkoutShoe, workout_id) is not None)


def shoe_out_for(s: Session, workout_id: str, w=None) -> sc.WorkoutShoeOut | None:
    """The resolved shoe of one workout, for the run detail."""
    w = w or s.execute(select(models.Workout).where(models.Workout.workout_id == workout_id)).scalar_one()
    shoe_id, source = shoes.resolve(s, [w])[workout_id]
    shoe = s.get(models.Shoe, shoe_id) if shoe_id is not None else None
    return None if shoe is None else sc.WorkoutShoeOut(id=shoe.id, name=shoe.name, retired=shoe.retired, source=source)


def router(api: Api) -> APIRouter:
    r = APIRouter(tags=["shoes"], dependencies=api.auth)

    def today(s: Session) -> str:
        return queue.local_today(settings.read(s, api.default_tz).home_tz)

    def listing(s: Session) -> sc.ShoesOut:
        tot = shoes.totals(s)
        rows = s.execute(select(models.Shoe).order_by(models.Shoe.id)).scalars()
        d = shoes.current_default(s, today(s))
        return sc.ShoesOut(
            shoes=[sc.ShoeOut(id=x.id, name=x.name, retired=x.retired, distance_m=tot.get(x.id, (0.0, 0))[0],
                              runs=tot.get(x.id, (0.0, 0))[1]) for x in rows],
            default=None if d is None else sc.ShoeDefaultOut(shoe_id=d.shoe_id, from_date=d.from_date))

    def name_taken(s: Session, name: str, except_id: int | None = None) -> bool:
        # casefold in Python: SQLite lower() folds ASCII only
        return any(i != except_id and n.casefold() == name.casefold()
                   for i, n in s.execute(select(models.Shoe.id, models.Shoe.name)).all())

    def commit_unique(s: Session) -> None:
        try:
            s.commit()
        except IntegrityError:  # a concurrent duplicate hit the unique index
            s.rollback()
            raise HTTPException(status_code=422, detail="a shoe with that name exists") from None

    @r.get("/shoes", response_model=sc.ShoesOut)
    def list_shoes() -> sc.ShoesOut:
        with Session(api.engine) as s:
            return listing(s)

    @r.post("/shoes", response_model=sc.ShoesOut, status_code=201)
    def add_shoe(body: sc.ShoeIn) -> sc.ShoesOut:
        with Session(api.engine) as s:
            if name_taken(s, body.name):
                raise HTTPException(status_code=422, detail="a shoe with that name exists")
            s.add(models.Shoe(name=body.name, retired=False, created_at=utcnow()))
            commit_unique(s)
            return listing(s)

    # declared before /shoes/{shoe_id} so "default" is never read as an id
    @r.put("/shoes/default", response_model=sc.ShoesOut)
    def set_default(body: sc.ShoeDefaultIn) -> sc.ShoesOut:
        with Session(api.engine) as s:
            if body.shoe_id is not None:
                shoe = s.get(models.Shoe, body.shoe_id)
                if shoe is None:
                    raise HTTPException(status_code=422, detail="unknown shoe")
                if shoe.retired:
                    raise HTTPException(status_code=422, detail="a retired shoe cannot be the default")
            row = s.get(models.ShoeDefault, body.from_date) or models.ShoeDefault(from_date=body.from_date)
            row.shoe_id = body.shoe_id
            s.add(row)
            s.commit()
            return listing(s)

    @r.patch("/shoes/{shoe_id}", response_model=sc.ShoesOut)
    def patch_shoe(shoe_id: int, body: sc.ShoePatch) -> sc.ShoesOut:
        with Session(api.engine) as s:
            shoe = s.get(models.Shoe, shoe_id)
            if shoe is None:
                raise HTTPException(status_code=404, detail="shoe not found")
            if body.name is not None:
                if name_taken(s, body.name, shoe_id):
                    raise HTTPException(status_code=422, detail="a shoe with that name exists")
                shoe.name = body.name
            if body.retired is not None:
                if body.retired and not shoe.retired:
                    t = today(s)
                    cur = shoes.current_default(s, t)
                    for fut in s.execute(select(models.ShoeDefault).where(
                            models.ShoeDefault.from_date > t, models.ShoeDefault.shoe_id == shoe_id)).scalars():
                        fut.shoe_id = None
                    # no default from tomorrow, so a run earlier today keeps its shoe
                    tomorrow = (date.fromisoformat(t) + timedelta(days=1)).isoformat()
                    if cur is not None and cur.shoe_id == shoe_id and s.get(models.ShoeDefault, tomorrow) is None:
                        s.add(models.ShoeDefault(from_date=tomorrow, shoe_id=None))
                shoe.retired = body.retired
            commit_unique(s)
            return listing(s)

    def require_workout(s: Session, workout_id: str) -> None:
        if s.execute(select(models.Workout.id).where(models.Workout.workout_id == workout_id)).first() is None:
            raise HTTPException(status_code=404, detail="workout not found")

    @r.put("/workouts/{workout_id}/shoe", response_model=sc.WorkoutShoeResult)
    def put_workout_shoe(workout_id: str, body: sc.WorkoutShoeIn) -> sc.WorkoutShoeResult:
        with Session(api.engine) as s:
            require_workout(s, workout_id)
            if body.shoe_id is not None and s.get(models.Shoe, body.shoe_id) is None:
                raise HTTPException(status_code=422, detail="unknown shoe")
            row = s.get(models.WorkoutShoe, workout_id) or models.WorkoutShoe(workout_id=workout_id)
            row.shoe_id, row.updated_at = body.shoe_id, utcnow()
            s.add(row)
            s.commit()
            return result_for(s, workout_id)

    @r.delete("/workouts/{workout_id}/shoe", response_model=sc.WorkoutShoeResult)
    def delete_workout_shoe(workout_id: str) -> sc.WorkoutShoeResult:
        with Session(api.engine) as s:
            require_workout(s, workout_id)
            row = s.get(models.WorkoutShoe, workout_id)
            if row is not None:
                s.delete(row)
                s.commit()
            return result_for(s, workout_id)

    return r

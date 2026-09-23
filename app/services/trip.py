import uuid

from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.gear import GearItem
from app.models.trip import (
    ChecklistItemKey,
    ChecklistStatus,
    FoodPlanner,
    Trip,
    TripChecklistItem,
    TripFood,
    TripGear,
    TripNote,
    TripType,
    shuttle_status_for,
)
from app.schemas.trip import (
    ChecklistItemUpdate,
    FoodPlannerUpdate,
    TripCreate,
    TripFoodCreate,
    TripFoodUpdate,
    TripGearCreate,
    TripGearUpdate,
    TripNoteCreate,
    TripNoteUpdate,
    TripUpdate,
    check_date_order,
)
from app.services.base import save_updates


async def create_trip(session: AsyncSession, user_id: uuid.UUID, data: TripCreate) -> Trip:
    # Direct construction (not model_validate) so the "init" event seeds checklist_items
    # and food_plan in memory; model_validate bypasses __init__ and would leave them unset,
    # forcing a lazy DB load on first access that fails under async (MissingGreenlet).
    trip = Trip(user_id=user_id, **data.model_dump())
    session.add(trip)
    await session.commit()
    result = await session.execute(select(Trip).where(Trip.id == trip.id))
    return result.scalar_one()


async def list_trips(session: AsyncSession, user_id: uuid.UUID) -> list[Trip]:
    # noinspection PyTypeChecker
    result = await session.execute(
        select(Trip)
        .where(Trip.user_id == user_id)
        .order_by(Trip.created_at)  # type: ignore[arg-type]
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def get_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip | None:
    # A plain select() (rather than session.get()) so the selectin-configured child
    # relationships are always populated via an awaited query, even if the Trip is already
    # in the session's identity map with those relationships unset (e.g. right after
    # create_trip in the same session) — session.get() would short-circuit on the identity
    # map hit and skip loading them, and accessing them later would need sync IO (MissingGreenlet).
    # populate_existing re-runs those loaders for an already-loaded Trip too, so children added or
    # removed earlier in the same session (e.g. copy_trip_gear) aren't served from a stale collection.
    result = await session.execute(
        select(Trip).where(Trip.id == trip_id).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def update_trip(session: AsyncSession, trip: Trip, data: TripUpdate) -> Trip:
    # The request may carry only one of the dates, so check the order against the stored values.
    sent = data.model_fields_set & {"start_date", "end_date"}
    start_date = data.start_date if "start_date" in sent else trip.start_date
    end_date = data.end_date if "end_date" in sent else trip.end_date
    try:
        check_date_order(start_date, end_date)
    except ValueError as exc:
        field = "end_date" if "end_date" in sent else "start_date"
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", field),
                    "msg": f"Value error, {exc}",
                    "input": getattr(data, field),
                }
            ]
        ) from exc
    if data.trip_type is not None and data.trip_type != trip.trip_type:
        _sync_shuttle_item(trip, data.trip_type)
    return await save_updates(session, trip, data)


def _sync_shuttle_item(trip: Trip, trip_type: TripType) -> None:
    # Keep the shuttle item in step with the trip type, but never undo a shuttle the user marked done.
    shuttle = next((i for i in trip.checklist_items if i.item == ChecklistItemKey.SHUTTLE_SCHEDULED), None)
    if shuttle is not None and shuttle.status != ChecklistStatus.DONE:
        shuttle.status = shuttle_status_for(trip_type)


async def delete_trip(session: AsyncSession, trip: Trip) -> None:
    await session.delete(trip)
    await session.commit()


async def get_trip_gear(
    session: AsyncSession, trip_id: uuid.UUID, trip_gear_id: uuid.UUID
) -> TripGear | None:
    result = await session.execute(
        select(TripGear).where(TripGear.id == trip_gear_id, TripGear.trip_id == trip_id)
    )
    return result.scalar_one_or_none()


async def list_trip_gear(session: AsyncSession, trip_id: uuid.UUID) -> list[TripGear]:
    result = await session.execute(
        select(TripGear).where(TripGear.trip_id == trip_id).order_by(col(TripGear.created_at))
    )
    return list(result.scalars().all())


async def add_trip_gear(
    session: AsyncSession, trip_id: uuid.UUID, item: GearItem, data: TripGearCreate
) -> TripGear:
    """Pack a closet item for a trip. The caller checks the item belongs to the trip's owner."""
    if item.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gear item is archived")
    existing = await session.execute(
        select(TripGear).where(TripGear.trip_id == trip_id, TripGear.gear_item_id == item.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gear item is already on this trip")
    trip_gear = TripGear(trip_id=trip_id, **data.model_dump())
    session.add(trip_gear)
    await session.commit()
    await session.refresh(trip_gear)
    return trip_gear


async def update_trip_gear(session: AsyncSession, trip_gear: TripGear, data: TripGearUpdate) -> TripGear:
    return await save_updates(session, trip_gear, data)


async def delete_trip_gear(session: AsyncSession, trip_gear: TripGear) -> None:
    await session.delete(trip_gear)
    await session.commit()


async def copy_trip_gear(session: AsyncSession, target: Trip, source: Trip) -> list[TripGear]:
    """Add the source trip's gear to the target trip, unpacked.

    Skips archived items and items the target already has, so copying is safe to repeat.
    """
    already_on_target = {tg.gear_item_id for tg in await list_trip_gear(session, target.id)}
    for tg in await list_trip_gear(session, source.id):
        if tg.gear_item_id in already_on_target or tg.gear_item.archived_at is not None:
            continue
        session.add(TripGear(trip_id=target.id, gear_item_id=tg.gear_item_id, quantity=tg.quantity))
    await session.commit()
    return await list_trip_gear(session, target.id)


async def add_note(session: AsyncSession, trip_id: uuid.UUID, data: TripNoteCreate) -> TripNote:
    note = TripNote(trip_id=trip_id, **data.model_dump())
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def get_note(session: AsyncSession, trip_id: uuid.UUID, note_id: uuid.UUID) -> TripNote | None:
    result = await session.execute(
        select(TripNote).where(TripNote.id == note_id, TripNote.trip_id == trip_id)
    )
    return result.scalar_one_or_none()


async def update_note(session: AsyncSession, note: TripNote, data: TripNoteUpdate) -> TripNote:
    return await save_updates(session, note, data)


async def delete_note(session: AsyncSession, note: TripNote) -> None:
    await session.delete(note)
    await session.commit()


async def get_checklist_item(
    session: AsyncSession, trip_id: uuid.UUID, item_key: ChecklistItemKey
) -> TripChecklistItem | None:
    result = await session.execute(
        select(TripChecklistItem).where(
            TripChecklistItem.trip_id == trip_id, TripChecklistItem.item == item_key
        )
    )
    return result.scalar_one_or_none()


async def update_checklist_item(
    session: AsyncSession, item: TripChecklistItem, data: ChecklistItemUpdate
) -> TripChecklistItem:
    return await save_updates(session, item, data)


async def update_food_planner(
    session: AsyncSession, planner: FoodPlanner, data: FoodPlannerUpdate
) -> FoodPlanner:
    return await save_updates(session, planner, data)


async def add_food_item(session: AsyncSession, planner_id: uuid.UUID, data: TripFoodCreate) -> TripFood:
    food = TripFood(planner_id=planner_id, **data.model_dump())
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


async def get_food_item(session: AsyncSession, planner_id: uuid.UUID, food_id: uuid.UUID) -> TripFood | None:
    result = await session.execute(
        select(TripFood).where(TripFood.id == food_id, TripFood.planner_id == planner_id)
    )
    return result.scalar_one_or_none()


async def update_food_item(session: AsyncSession, food: TripFood, data: TripFoodUpdate) -> TripFood:
    return await save_updates(session, food, data)


async def delete_food_item(session: AsyncSession, food: TripFood) -> None:
    await session.delete(food)
    await session.commit()

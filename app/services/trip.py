import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.trip import ChecklistItemKey, FoodPlanner, Gear, Trip, TripChecklistItem, TripFood, TripNote
from app.schemas.trip import (
    ChecklistItemUpdate,
    FoodPlannerUpdate,
    GearCreate,
    GearUpdate,
    TripCreate,
    TripFoodCreate,
    TripFoodUpdate,
    TripNoteCreate,
    TripNoteUpdate,
    TripUpdate,
)


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
        select(Trip).where(Trip.user_id == user_id).order_by(Trip.created_at)  # type: ignore[arg-type]
    )
    return list(result.scalars().all())


async def get_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip | None:
    # A plain select() (rather than session.get()) so the selectin-configured child
    # relationships are always populated via an awaited query, even if the Trip is already
    # in the session's identity map with those relationships unset (e.g. right after
    # create_trip in the same session) — session.get() would short-circuit on the identity
    # map hit and skip loading them, and accessing them later would need sync IO (MissingGreenlet).
    result = await session.execute(select(Trip).where(Trip.id == trip_id))
    return result.scalar_one_or_none()


async def update_trip(session: AsyncSession, trip: Trip, data: TripUpdate) -> Trip:
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(trip, key, value)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return trip


async def delete_trip(session: AsyncSession, trip: Trip) -> None:
    await session.delete(trip)
    await session.commit()


async def add_gear(session: AsyncSession, trip_id: uuid.UUID, data: GearCreate) -> Gear:
    gear = Gear(trip_id=trip_id, **data.model_dump())
    session.add(gear)
    await session.commit()
    await session.refresh(gear)
    return gear


async def get_gear(session: AsyncSession, trip_id: uuid.UUID, gear_id: uuid.UUID) -> Gear | None:
    result = await session.execute(select(Gear).where(Gear.id == gear_id, Gear.trip_id == trip_id))
    return result.scalar_one_or_none()


async def update_gear(session: AsyncSession, gear: Gear, data: GearUpdate) -> Gear:
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(gear, key, value)
    session.add(gear)
    await session.commit()
    await session.refresh(gear)
    return gear


async def delete_gear(session: AsyncSession, gear: Gear) -> None:
    await session.delete(gear)
    await session.commit()


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
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(note, key, value)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


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
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(item, key, value)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_food_planner(
    session: AsyncSession, planner: FoodPlanner, data: FoodPlannerUpdate
) -> FoodPlanner:
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(planner, key, value)
    session.add(planner)
    await session.commit()
    await session.refresh(planner)
    return planner


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
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(food, key, value)
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


async def delete_food_item(session: AsyncSession, food: TripFood) -> None:
    await session.delete(food)
    await session.commit()

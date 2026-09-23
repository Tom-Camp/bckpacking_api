from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.auth.passwords import hash_password
from app.models import FoodPlanner, Gear, Trip, TripChecklistItem, TripFood, TripNote, User
from app.models.trip import ChecklistItemKey, Meal, TripType

hashed_password: str = hash_password("r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD")


async def _make_user(session: AsyncSession, email: str = "hiker@example.com") -> User:
    user = User(email=email, password_hash=hashed_password, username=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_trip(session: AsyncSession, user: User, **kwargs: object) -> Trip:
    kwargs.setdefault("name", "Test Trip")
    kwargs.setdefault("total_distance_m", 16_000)
    trip = Trip(user_id=user.id, **kwargs)
    session.add(trip)
    await session.commit()
    # Deliberately not refreshing: all Trip fields have client-side defaults set at
    # construction, and refresh() would eagerly populate the "selectin" gear_list/food_plan
    # relationships (empty, at this point), leaving a stale cache for later queries in tests
    # that add children afterwards within the same session.
    return trip


def test_trip_name_is_required() -> None:
    # SQLModel table classes skip Pydantic validation on direct __init__ (needed so the
    # ORM can construct partially-populated instances while loading rows), so required-field
    # enforcement only shows up through model_validate(), e.g. FastAPI request parsing.
    with pytest.raises(ValidationError, match="name"):
        Trip.model_validate({"user_id": uuid4()})


async def test_trip_defaults(session: AsyncSession) -> None:
    user = await _make_user(session)
    trip = await _make_trip(session, user, name="Wonderland Trail", total_distance_m=149_700)

    assert trip.trip_type == TripType.LOOP
    assert {item.item for item in trip.checklist_items} == set(ChecklistItemKey)
    assert all(item.checked is False and item.details is None for item in trip.checklist_items)
    assert trip.food_plan is not None
    assert trip.food_plan.target_kcal_per_day == 2700
    assert trip.food_plan.target_food_g_per_day == 794


async def test_checklist_item_can_be_updated_and_queried_individually(session: AsyncSession) -> None:
    user = await _make_user(session, "checklist@example.com")
    trip = Trip(name="Checklist Trip", total_distance_m=16_000, user_id=user.id)
    session.add(trip)
    await session.commit()

    water_item = next(i for i in trip.checklist_items if i.item == ChecklistItemKey.WATER_SOURCES)
    water_item.checked = True
    water_item.details = "Two reliable springs"
    await session.commit()

    result = await session.execute(
        select(TripChecklistItem).where(col(TripChecklistItem.trip_id) == trip.id)
    )
    items = {i.item: i for i in result.scalars().all()}

    assert items[ChecklistItemKey.WATER_SOURCES].checked is True
    assert items[ChecklistItemKey.WATER_SOURCES].details == "Two reliable springs"
    assert items[ChecklistItemKey.FIRE_RESTRICTIONS].checked is False


async def test_checklist_items_are_unique_per_trip_and_item(session: AsyncSession) -> None:
    user = await _make_user(session, "dup-checklist@example.com")
    trip = await _make_trip(session, user)

    session.add(TripChecklistItem(trip_id=trip.id, item=ChecklistItemKey.WATER_SOURCES))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_gear_category_is_lowercased(session: AsyncSession) -> None:
    # Table classes bypass Pydantic validation on direct __init__, so the validator only
    # runs via model_validate() (how FastAPI builds models from request payloads).
    user = await _make_user(session, "gear@example.com")
    trip = await _make_trip(session, user)

    gear = Gear.model_validate(
        {"gear_name": "Tent", "category": "SHELTER", "weight_g": 1200, "quantity": 1, "trip_id": trip.id}
    )
    session.add(gear)
    await session.commit()
    await session.refresh(gear)

    assert gear.category == "shelter"


async def test_trip_gear_list_relationship(session: AsyncSession) -> None:
    user = await _make_user(session, "gearlist@example.com")
    trip = await _make_trip(session, user)

    session.add_all(
        [
            Gear(gear_name="Tent", category="shelter", weight_g=1200, quantity=1, trip_id=trip.id),
            Gear(gear_name="Stove", category="cook", weight_g=500, quantity=1, trip_id=trip.id),
        ]
    )
    await session.commit()

    result = await session.execute(
        select(Trip).options(selectinload(Trip.gear_list)).where(col(Trip.id) == trip.id)  # type: ignore[arg-type]
    )
    loaded_trip = result.scalar_one()

    assert {g.category for g in loaded_trip.gear_list} == {"shelter", "cook"}


async def test_trip_notes_relationship(session: AsyncSession) -> None:
    user = await _make_user(session, "notes@example.com")
    trip = await _make_trip(session, user)

    session.add_all(
        [
            TripNote(content="Bring extra socks.", trip_id=trip.id),
            TripNote(content="Check permit deadline.", trip_id=trip.id),
        ]
    )
    await session.commit()

    result = await session.execute(
        select(Trip).options(selectinload(Trip.notes)).where(col(Trip.id) == trip.id)  # type: ignore[arg-type]
    )
    loaded_trip = result.scalar_one()

    assert {n.content for n in loaded_trip.notes} == {"Bring extra socks.", "Check permit deadline."}


async def test_food_planner_and_trip_food_relationship(session: AsyncSession) -> None:
    user = await _make_user(session, "food@example.com")
    trip = await _make_trip(session, user)
    planner = trip.food_plan
    assert planner is not None
    planner.target_kcal_per_day = 3000
    planner.target_food_g_per_day = 900
    session.add(planner)
    await session.commit()

    session.add_all(
        [
            TripFood(
                day="Day 1",
                name="Oatmeal",
                meal_type=Meal.BREAKFAST,
                weight_g=100,
                kcal=400,
                planner_id=planner.id,
            ),
            TripFood(
                day="Day 1",
                name="Trail Mix",
                meal_type=Meal.SNACK,
                weight_g=200,
                kcal=600,
                planner_id=planner.id,
            ),
        ]
    )
    await session.commit()

    result = await session.execute(
        select(FoodPlanner)
        .options(selectinload(FoodPlanner.food))  # type: ignore[arg-type]
        .where(col(FoodPlanner.id) == planner.id)
    )
    loaded_planner = result.scalar_one()

    assert {f.name for f in loaded_planner.food} == {"Oatmeal", "Trail Mix"}
    assert sum(f.kcal for f in loaded_planner.food) == 1000


async def test_food_planner_trip_id_is_unique(session: AsyncSession) -> None:
    user = await _make_user(session, "oneplanner@example.com")
    trip = await _make_trip(session, user)  # already has an auto-seeded FoodPlanner

    session.add(FoodPlanner(trip_id=trip.id))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_trip_cascades_to_gear_food_planner_checklist_items_and_notes(
    session: AsyncSession,
) -> None:
    user = await _make_user(session, "cascade@example.com")
    trip = await _make_trip(session, user)

    session.add_all(
        [
            Gear(gear_name="Tent", category="shelter", weight_g=1000, quantity=1, trip_id=trip.id),
            TripNote(content="Bring extra socks.", trip_id=trip.id),
        ]
    )
    await session.commit()

    await session.delete(trip)
    await session.commit()

    remaining_gear = (await session.execute(select(Gear))).scalars().all()
    remaining_planners = (await session.execute(select(FoodPlanner))).scalars().all()
    remaining_checklist_items = (await session.execute(select(TripChecklistItem))).scalars().all()
    remaining_notes = (await session.execute(select(TripNote))).scalars().all()

    assert remaining_gear == []
    assert remaining_planners == []
    assert remaining_checklist_items == []
    assert remaining_notes == []


async def test_deleting_food_planner_cascades_to_trip_food(session: AsyncSession) -> None:
    user = await _make_user(session, "cascade-food@example.com")
    trip = await _make_trip(session, user)
    planner = trip.food_plan
    assert planner is not None

    session.add(
        TripFood(
            day="Day 1",
            name="Oatmeal",
            weight_g=100,
            kcal=400,
            planner_id=planner.id,
        )
    )
    await session.commit()

    await session.delete(planner)
    await session.commit()

    remaining_food = (await session.execute(select(TripFood))).scalars().all()

    assert remaining_food == []


async def test_trip_end_date_before_start_date_violates_check_constraint(session: AsyncSession) -> None:
    user = await _make_user(session, "dates@example.com")

    session.add(
        Trip(name="Backwards", user_id=user.id, start_date=date(2026, 8, 26), end_date=date(2026, 8, 25))
    )
    with pytest.raises(IntegrityError):
        await session.commit()

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.auth.passwords import hash_password
from app.models import FoodPlanner, Gear, Trip, TripFood, User
from app.models.trip import CHECKLIST_ITEMS, ChecklistItem, Meal, TripType, Unit

hashed_password: str = hash_password("r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD")


async def _make_user(session: AsyncSession, email: str = "hiker@example.com") -> User:
    user = User(email=email, password_hash=hashed_password, username=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_trip(session: AsyncSession, user: User, **kwargs: object) -> Trip:
    kwargs.setdefault("name", "Test Trip")
    kwargs.setdefault("total_distance", 10)
    trip = Trip(user_id=user.id, **kwargs)
    session.add(trip)
    await session.commit()
    # Deliberately not refreshing: all Trip fields have client-side defaults set at
    # construction, and refresh() would eagerly populate the "selectin" gear_list/food_plan
    # relationships (empty, at this point), leaving a stale cache for later queries in tests
    # that add children afterwards within the same session.
    return trip


def test_total_distance_is_required() -> None:
    # SQLModel table classes skip Pydantic validation on direct __init__ (needed so the
    # ORM can construct partially-populated instances while loading rows), so required-field
    # enforcement only shows up through model_validate(), e.g. FastAPI request parsing.
    with pytest.raises(ValidationError):
        Trip.model_validate({"name": "No distance"})


async def test_omitting_total_distance_violates_not_null_at_the_db_level(session: AsyncSession) -> None:
    user = await _make_user(session, "notnull@example.com")
    trip = Trip(name="No distance", user_id=user.id)  # type: ignore[call-arg]
    trip.total_distance = None  # type: ignore[assignment]
    session.add(trip)

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_trip_defaults(session: AsyncSession) -> None:
    user = await _make_user(session)
    trip = await _make_trip(session, user, name="Wonderland Trail", total_distance=93)

    assert trip.measurements == Unit.IMPERIAL
    assert trip.trip_type == TripType.LOOP
    assert trip.permit_required is False
    assert set(trip.checklist) == set(CHECKLIST_ITEMS)
    assert all(isinstance(item, ChecklistItem) and item.checked is False for item in trip.checklist.values())


async def test_checklist_round_trips_through_json_column(session: AsyncSession) -> None:
    user = await _make_user(session, "checklist@example.com")
    trip = Trip(name="Checklist Trip", total_distance=10, user_id=user.id)
    trip.set_checklist_item("water_sources", ChecklistItem(checked=True, details="Two reliable springs"))
    session.add(trip)
    await session.commit()

    result = await session.execute(select(Trip).where(col(Trip.id) == trip.id))
    reloaded = result.scalar_one()

    assert reloaded.checklist["water_sources"].checked is True
    assert reloaded.checklist["water_sources"].details == "Two reliable springs"
    assert reloaded.checklist["fire_restrictions"].checked is False


def test_checklist_item_is_frozen() -> None:
    item = ChecklistItem()
    with pytest.raises(ValidationError):
        item.checked = True  # type: ignore[misc]


async def test_gear_category_is_lowercased(session: AsyncSession) -> None:
    # Table classes bypass Pydantic validation on direct __init__, so the validator only
    # runs via model_validate() (how FastAPI builds models from request payloads).
    user = await _make_user(session, "gear@example.com")
    trip = await _make_trip(session, user)

    gear = Gear.model_validate({"category": "SHELTER", "weight": 1.2, "quantity": 1, "trip_id": trip.id})
    session.add(gear)
    await session.commit()
    await session.refresh(gear)

    assert gear.category == "shelter"


async def test_trip_gear_list_relationship(session: AsyncSession) -> None:
    user = await _make_user(session, "gearlist@example.com")
    trip = await _make_trip(session, user)

    session.add_all(
        [
            Gear(category="shelter", weight=1.2, quantity=1, trip_id=trip.id),
            Gear(category="cook", weight=0.5, quantity=1, trip_id=trip.id),
        ]
    )
    await session.commit()

    result = await session.execute(
        select(Trip).options(selectinload(Trip.gear_list)).where(col(Trip.id) == trip.id)  # type: ignore[arg-type]
    )
    loaded_trip = result.scalar_one()

    assert {g.category for g in loaded_trip.gear_list} == {"shelter", "cook"}


async def test_food_planner_and_trip_food_relationship(session: AsyncSession) -> None:
    user = await _make_user(session, "food@example.com")
    trip = await _make_trip(session, user)

    planner = FoodPlanner(target_calories=12000, target_food_weight=6.5, trip_id=trip.id)
    session.add(planner)
    await session.commit()
    # Not refreshing: planner.id is already set client-side and refresh() would eagerly
    # populate the "selectin" food relationship (empty, at this point) into the session cache.

    session.add_all(
        [
            TripFood(
                day="Day 1",
                name="Oatmeal",
                meal_type=Meal.BREAKFAST,
                weight=0.1,
                calories=400,
                planner_id=planner.id,
            ),
            TripFood(
                day="Day 1",
                name="Trail Mix",
                meal_type=Meal.SNACK,
                weight=0.2,
                calories=600,
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
    assert sum(f.calories for f in loaded_planner.food) == 1000


async def test_food_planner_trip_id_is_unique(session: AsyncSession) -> None:
    user = await _make_user(session, "oneplanner@example.com")
    trip = await _make_trip(session, user)

    session.add(FoodPlanner(trip_id=trip.id))
    await session.commit()

    session.add(FoodPlanner(trip_id=trip.id))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_trip_cascades_to_gear_and_food_planner(session: AsyncSession) -> None:
    user = await _make_user(session, "cascade@example.com")
    trip = await _make_trip(session, user)

    session.add_all(
        [
            Gear(category="shelter", weight=1.0, quantity=1, trip_id=trip.id),
            FoodPlanner(trip_id=trip.id),
        ]
    )
    await session.commit()

    await session.delete(trip)
    await session.commit()

    remaining_gear = (await session.execute(select(Gear))).scalars().all()
    remaining_planners = (await session.execute(select(FoodPlanner))).scalars().all()

    assert remaining_gear == []
    assert remaining_planners == []


async def test_deleting_food_planner_cascades_to_trip_food(session: AsyncSession) -> None:
    user = await _make_user(session, "cascade-food@example.com")
    trip = await _make_trip(session, user)

    planner = FoodPlanner(trip_id=trip.id)
    session.add(planner)
    await session.commit()
    await session.refresh(planner)

    session.add(
        TripFood(
            day="Day 1",
            name="Oatmeal",
            weight=0.1,
            calories=400,
            planner_id=planner.id,
        )
    )
    await session.commit()

    await session.delete(planner)
    await session.commit()

    remaining_food = (await session.execute(select(TripFood))).scalars().all()

    assert remaining_food == []

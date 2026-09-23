import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.models import GearItem, GearKind, Trip, TripGear, User

hashed_password: str = hash_password("r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD")


async def _make_user_with_trip_and_item(session: AsyncSession, email: str) -> tuple[User, Trip, GearItem]:
    user = User(email=email, password_hash=hashed_password, username=email)
    session.add(user)
    await session.commit()
    trip = Trip(name="Test Trip", user_id=user.id)
    item = GearItem(user_id=user.id, name="Tent", category="shelter", weight_g=1200)
    session.add_all([trip, item])
    await session.commit()
    return user, trip, item


async def test_gear_item_defaults_and_category_is_lowercased(session: AsyncSession) -> None:
    # Table classes bypass Pydantic validation on direct __init__, so the validator only
    # runs via model_validate() (how FastAPI builds models from request payloads).
    _, _, owner_item = await _make_user_with_trip_and_item(session, "gear@example.com")

    item = GearItem.model_validate({"user_id": owner_item.user_id, "name": "Quilt", "category": "SLEEP"})
    session.add(item)
    await session.commit()
    await session.refresh(item)

    assert item.category == "sleep"
    assert item.kind == GearKind.BASE
    assert item.weight_g == 0
    assert item.archived_at is None


async def test_trip_gear_is_unique_per_trip_and_item(session: AsyncSession) -> None:
    _, trip, item = await _make_user_with_trip_and_item(session, "dup-gear@example.com")
    session.add(TripGear(trip_id=trip.id, gear_item_id=item.id))
    await session.commit()

    session.add(TripGear(trip_id=trip.id, gear_item_id=item.id))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_gear_item_used_by_a_trip_cannot_be_hard_deleted(session: AsyncSession) -> None:
    _, trip, item = await _make_user_with_trip_and_item(session, "in-use@example.com")
    session.add(TripGear(trip_id=trip.id, gear_item_id=item.id))
    await session.commit()

    await session.delete(item)
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_user_removes_trips_closet_and_trip_gear(session: AsyncSession) -> None:
    # Both trips and closet items cascade from the user; the TripGear -> GearItem FK has no
    # ON DELETE, so this only works because that FK is checked at commit (DEFERRABLE INITIALLY DEFERRED).
    user, trip, item = await _make_user_with_trip_and_item(session, "leaving@example.com")
    session.add(TripGear(trip_id=trip.id, gear_item_id=item.id))
    await session.commit()

    await session.delete(user)
    await session.commit()

    for model in (Trip, GearItem, TripGear):
        assert (await session.execute(select(model))).scalars().all() == []

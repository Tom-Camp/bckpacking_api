import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.auth.passwords import hash_password
from app.models import Trip, User
from app.models.user import UserRole, UserStatus

hashed_password = hash_password("r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD")


async def test_create_user_applies_defaults(session: AsyncSession) -> None:
    user = User(
        email="defaults@example.com",
        username="Hiker1",
        password_hash=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert user.status == UserStatus.ACTIVE
    assert user.role == UserRole.USER
    assert user.username == "Hiker1"
    assert user.password_hash is not None


async def test_email_must_be_unique(session: AsyncSession) -> None:
    session.add(
        User(
            email="dup@example.com",
            username="Hiker2",
            password_hash=hashed_password,
        )
    )
    await session.commit()

    session.add(
        User(
            email="dup@example.com",
            username="Hiker3",
            password_hash=hashed_password,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_username_must_be_unique(session: AsyncSession) -> None:
    session.add(
        User(
            email="a@example.com",
            username="be_unique",
            password_hash=hashed_password,
        )
    )
    await session.commit()

    session.add(
        User(
            email="b@example.com",
            username="be_unique",
            password_hash=hashed_password,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_username_required(session: AsyncSession) -> None:
    session.add(
        User(
            email="username_required@example.com",
            password_hash=hashed_password,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_password_required(session: AsyncSession) -> None:
    session.add(
        User(  # type: ignore[call-arg]
            email="password_required@example.com",
            username="password_required",
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_user_trips_relationship(session: AsyncSession) -> None:
    user = User(
        email="relation@example.com",
        username="ship",
        password_hash=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip = Trip(name="PCT Section A", total_distance_m=42_000, user_id=user.id)
    session.add(trip)
    await session.commit()

    result = await session.execute(
        select(User).options(selectinload(User.trips)).where(col(User.id) == user.id)  # type: ignore[arg-type]
    )
    loaded_user = result.scalar_one()

    assert [t.name for t in loaded_user.trips] == ["PCT Section A"]

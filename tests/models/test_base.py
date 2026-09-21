import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.models import User

hashed_password: str = hash_password("r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD")


async def test_id_is_generated_as_uuid(session: AsyncSession) -> None:
    user = User(
        email="uuid-test@example.com",
        username="test_base_hiker",
        password_hash=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert isinstance(user.id, UUID)


async def test_created_at_and_updated_at_are_set_on_insert(session: AsyncSession) -> None:
    user = User(
        email="timestamp@example.com",
        username="test_base2_hiker",
        password_hash=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert user.created_at is not None
    assert user.updated_at is not None


async def test_updated_at_changes_on_update_but_created_at_does_not(session: AsyncSession) -> None:
    user = User(
        email="updated@example.com",
        username="test_base3_hiker",
        password_hash=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    original_created_at = user.created_at
    original_updated_at = user.updated_at

    await asyncio.sleep(0.01)
    user.first_name = "Ada"
    await session.commit()
    await session.refresh(user)

    assert user.created_at == original_created_at
    assert user.updated_at > original_updated_at


async def test_string_columns_are_stripped_on_write(session: AsyncSession) -> None:
    user = User(
        email="      strip@example.com",
        username="test_base4_hiker",
        password_hash=hashed_password,
        first_name="Ada",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert user.email == "strip@example.com"
    assert user.first_name == "Ada"

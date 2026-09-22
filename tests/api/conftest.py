from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.db import get_session
from app.main import app
from app.models.user import User, UserStatus

_PASSWORD = "r1GRB3$ZB0*mbwymrJuJcdUTtdqESdf%AuD"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def _get_session_override() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _get_session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_active_user(session: AsyncSession, email: str, username: str) -> User:
    db_user = User(
        email=email,
        password_hash=hash_password(_PASSWORD),
        username=username,
        status=UserStatus.ACTIVE,
    )
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    return await _make_active_user(session, "hiker@example.com", "hiker")


@pytest_asyncio.fixture
async def other_user(session: AsyncSession) -> User:
    return await _make_active_user(session, "other-hiker@example.com", "other-hiker")


@pytest.fixture
def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def other_auth_headers(other_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_user.id)}"}

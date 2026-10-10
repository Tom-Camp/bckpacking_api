import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User, UserRole, UserStatus
from app.services import user as user_service
from app.utils.config import settings
from tests.api.conftest import _PASSWORD, _make_active_user


async def _register(client: AsyncClient, email: str, username: str) -> int:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD, "username": username}
    )
    return response.status_code


async def test_register_stores_email_lowercased(client: AsyncClient, session: AsyncSession) -> None:
    assert await _register(client, "Tom@Example.com", "tom") == 201

    result = await session.execute(select(User).where(User.username == "tom"))
    assert result.scalar_one().email == "tom@example.com"


async def test_register_rejects_case_variant_of_existing_email(client: AsyncClient) -> None:
    assert await _register(client, "Tom@Example.com", "tom") == 201

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "tom@example.com", "password": _PASSWORD, "username": "tom2"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


async def test_login_is_case_insensitive(client: AsyncClient) -> None:
    assert await _register(client, "Tom@Example.com", "tom") == 201

    for email in ("Tom@Example.com", "tom@example.com", "TOM@EXAMPLE.COM"):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
        assert response.status_code == 200, email


@pytest.mark.parametrize("variant", ["OWNER@example.com", "Owner@EXAMPLE.com"])
async def test_admin_email_case_variant_cannot_register_second_admin(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    monkeypatch.setattr(settings, "admin_email", "owner@example.com")
    assert await _register(client, "owner@example.com", "owner") == 201

    assert await _register(client, variant, "impostor") == 409
    # The test client shares one session across requests; a real request would get a fresh one
    await session.rollback()

    admins = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    assert [u.username for u in admins.scalars()] == ["owner"]


async def test_register_non_admin_email_gets_user_role(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_email", "owner@example.com")
    assert await _register(client, "someone@example.com", "someone") == 201

    result = await session.execute(select(User).where(User.username == "someone"))
    assert result.scalar_one().role == UserRole.USER


async def test_admin_email_with_different_case_still_bootstraps_admin(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_email", " Owner@Example.com ")
    assert await _register(client, "owner@example.com", "owner") == 201

    result = await session.execute(select(User).where(User.username == "owner"))
    owner = result.scalar_one()
    assert owner.role == UserRole.ADMIN
    assert owner.status == UserStatus.ACTIVE


async def test_ensure_admin_matches_email_case_insensitively(session: AsyncSession) -> None:
    owner = await _make_active_user(session, "owner@example.com", "owner")
    assert owner.role == UserRole.USER

    await user_service.ensure_admin(session, "Owner@Example.com")

    await session.refresh(owner)
    assert owner.role == UserRole.ADMIN
    assert owner.status == UserStatus.ACTIVE

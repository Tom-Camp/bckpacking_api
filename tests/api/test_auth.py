import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.tokens import create_access_token
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


async def _login(client: AsyncClient, email: str, password: str = _PASSWORD) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_register_then_login_returns_a_working_bearer_token(client: AsyncClient) -> None:
    assert await _register(client, "new@example.com", "newbie") == 201

    response = await _login(client, "new@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "newbie"


async def test_register_rejects_duplicate_username(client: AsyncClient) -> None:
    assert await _register(client, "first@example.com", "taken") == 201

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": _PASSWORD, "username": "taken"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Username already taken"


async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "password1", "username": "weak"},
    )

    assert response.status_code == 422


async def test_wrong_password_and_unknown_email_get_the_same_401(client: AsyncClient, user: User) -> None:
    wrong_password = await _login(client, user.email, "not-the-password")
    unknown_email = await _login(client, "nobody@example.com")

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_blocked_user_cannot_log_in(client: AsyncClient, session: AsyncSession, user: User) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    response = await _login(client, user.email)

    assert response.status_code == 403
    assert response.json()["detail"] == "Account suspended"


async def test_first_login_is_set_once_and_last_login_on_every_login(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    assert user.first_login is None and user.last_login is None

    assert (await _login(client, user.email)).status_code == 200
    await session.refresh(user)
    first_login, last_login = user.first_login, user.last_login
    assert first_login is not None and last_login == first_login

    assert (await _login(client, user.email)).status_code == 200
    await session.refresh(user)
    assert user.first_login == first_login
    assert user.last_login is not None and user.last_login > last_login


def _token(payload: dict[str, object], secret: str = settings.jwt_secret) -> str:
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def _bad_tokens(user_id: uuid.UUID) -> dict[str, str]:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=5)
    return {
        "malformed": "not-a-jwt",
        "expired": _token(
            {"sub": str(user_id), "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)}
        ),
        "wrong_secret": _token({"sub": str(user_id), "exp": exp}, secret="another-secret-" + "x" * 32),
        "no_sub": _token({"exp": exp}),
        "sub_not_uuid": _token({"sub": "hiker", "exp": exp}),
        "unknown_user": create_access_token(uuid.uuid4()),
    }


@pytest.mark.parametrize(
    "case", ["malformed", "expired", "wrong_secret", "no_sub", "sub_not_uuid", "unknown_user"]
)
async def test_bad_token_gets_401(client: AsyncClient, user: User, case: str) -> None:
    token = _bad_tokens(user.id)[case]

    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_missing_token_gets_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401


async def test_token_for_a_deleted_user_gets_401(
    client: AsyncClient, session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    await user_service.delete_user(session, user)

    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"


async def test_blocked_users_token_reads_own_profile_but_nothing_else(
    client: AsyncClient, session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    trips = await client.get("/api/v1/trips", headers=auth_headers)
    # /users/me deliberately only needs get_current_user, so the UI can show the account state
    me = await client.get("/api/v1/users/me", headers=auth_headers)

    assert trips.status_code == 403
    assert trips.json()["detail"] == "Account suspended"
    assert me.status_code == 200
    assert me.json()["status"] == "blocked"

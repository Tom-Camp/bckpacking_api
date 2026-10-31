import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.v1.auth import EMAIL_NOT_VERIFIED
from app.auth.tokens import create_access_token
from app.models.user import User, UserRole, UserStatus
from app.services import user as user_service
from app.utils.config import settings
from scripts.seed import seed
from scripts.seed_data import USERS
from tests.api.conftest import _PASSWORD, _make_active_user

_SEED_PASSWORD = "test-only-ridgeline-cairn-7"  # nosec B105


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


async def test_login_is_case_insensitive(client: AsyncClient, session: AsyncSession) -> None:
    assert await _register(client, "Tom@Example.com", "tom") == 201
    tom = await user_service.get_user_by_username(session, "tom")
    assert tom is not None
    await user_service.mark_email_verified(session, tom)

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


async def test_admin_email_user_cannot_log_in_until_verified(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, outbox: list[dict[str, str]]
) -> None:
    # Whoever registers with ADMIN_EMAIL first gets admin, so they must prove they own the inbox (#42)
    monkeypatch.setattr(settings, "admin_email", "owner@example.com")
    assert await _register(client, "owner@example.com", "owner") == 201

    refused = await _login(client, "owner@example.com")
    await _verify_from(client, outbox[0])
    allowed = await _login(client, "owner@example.com")

    assert refused.status_code == 403
    assert refused.json()["detail"] == EMAIL_NOT_VERIFIED
    assert allowed.status_code == 200


async def test_ensure_admin_matches_email_case_insensitively(session: AsyncSession) -> None:
    owner = await _make_active_user(session, "owner@example.com", "owner")
    assert owner.role == UserRole.USER

    await user_service.ensure_admin(session, "Owner@Example.com")

    await session.refresh(owner)
    assert owner.role == UserRole.ADMIN
    assert owner.status == UserStatus.ACTIVE


async def _login(client: AsyncClient, email: str, password: str = _PASSWORD) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _verify_from(client: AsyncClient, message: dict[str, str]) -> None:
    prefix = "https://ui.example/verify-email#"
    [line] = [line for line in message["text"].splitlines() if line.startswith(prefix)]
    response = await client.post("/api/v1/auth/verify-email", json={"token": line.removeprefix(prefix)})
    assert response.status_code == 204


async def test_register_then_login_returns_a_working_bearer_token(
    client: AsyncClient, outbox: list[dict[str, str]]
) -> None:
    assert await _register(client, "new@example.com", "newbie") == 201
    await _verify_from(client, outbox[0])

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

    # The UI shows this body, so it must stay exactly what a pydantic field validator produces.
    assert response.status_code == 422
    assert response.content == (
        b'{"detail":[{"type":"value_error","loc":["body","password"],'
        b'"msg":"Value error, This is a very common password.","input":"password1","ctx":{"error":{}}}]}'
    )


async def test_register_rejects_password_over_72_bytes_without_zxcvbn(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user_service, "check_password_strength", _never_called)

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "long@example.com", "password": _PASSWORD * 3, "username": "long"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert response.json()["detail"][0]["msg"] == "Value error, Password must be at most 72 bytes"


def _never_called(*_args: object) -> None:
    raise AssertionError("zxcvbn must not run")


async def test_wrong_password_and_unknown_email_get_the_same_401(client: AsyncClient, user: User) -> None:
    wrong_password = await _login(client, user.email, "not-the-password")
    unknown_email = await _login(client, "nobody@example.com")

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


@pytest.mark.parametrize("verified", [True, False])
async def test_blocked_user_cannot_log_in(
    client: AsyncClient, session: AsyncSession, verified: bool
) -> None:
    user = await _make_active_user(session, "blocked@example.com", "blocked", verified=verified)
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


async def test_seeded_accounts_can_log_in(client: AsyncClient, session: AsyncSession) -> None:
    await seed(session, _SEED_PASSWORD)

    statuses = {u.username: (await _login(client, u.email, _SEED_PASSWORD)).status_code for u in USERS}

    assert statuses == {u.username: 403 if u.status == UserStatus.BLOCKED else 200 for u in USERS}


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
        "no_ver": _token({"sub": str(user_id), "exp": exp}),
        "ver_not_int": _token({"sub": str(user_id), "ver": "0", "exp": exp}),
        "ver_bool": _token({"sub": str(user_id), "ver": False, "exp": exp}),
        "stale_ver": _token({"sub": str(user_id), "ver": -1, "exp": exp}),
        "unknown_user": create_access_token(
            User(id=uuid.uuid4(), email="x", username="x", password_hash="x")  # noqa: S106
        ),
    }


@pytest.mark.parametrize(
    "case",
    [
        "malformed",
        "expired",
        "wrong_secret",
        "no_sub",
        "sub_not_uuid",
        "no_ver",
        "ver_not_int",
        "ver_bool",
        "stale_ver",
        "unknown_user",
    ],
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

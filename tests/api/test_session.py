from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.auth.tokens import create_access_token
from app.db import get_session
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole, UserStatus
from app.services import refresh_token as refresh_token_service
from app.utils.config import settings
from tests.api.conftest import _PASSWORD, _make_active_user

_NEW_PASSWORD = "Ziv8%quartz-Lantern!muskeg"  # nosec B105
_RESET_PREFIX = "https://ui.example/reset-password#"


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    # https, unlike the shared fixture: httpx won't send a Secure cookie over http://
    async def _get_session_override() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _get_session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _cookie(response: Response) -> str:
    raw = response.cookies.get("refresh_token")
    assert raw, response.headers.get_list("set-cookie")
    return raw


def _set_cookie_header(response: Response) -> str:
    [header] = [h for h in response.headers.get_list("set-cookie") if h.startswith("refresh_token=")]
    return header


def _assert_cleared(response: Response) -> None:
    header = _set_cookie_header(response).lower()
    assert header.startswith('refresh_token=""') or header.startswith("refresh_token=;")
    assert "max-age=0" in header
    assert "path=/api/v1/session" in header


async def _login(client: AsyncClient, password: str = _PASSWORD) -> Response:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "hiker@example.com", "password": password}
    )
    assert response.status_code == 200, response.text
    return response


async def _refresh(client: AsyncClient, raw: str | None) -> Response:
    # Send exactly this cookie, whatever the client's jar holds
    client.cookies.clear()
    headers = {"Cookie": f"refresh_token={raw}"} if raw is not None else {}
    return await client.post("/api/v1/session/refresh", headers=headers)


async def _me_status(client: AsyncClient, access_token: str) -> int:
    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    return response.status_code


def _shift_clock(monkeypatch: pytest.MonkeyPatch, delta: timedelta) -> None:
    monkeypatch.setattr(refresh_token_service, "_now", lambda: datetime.now(UTC) + delta)


async def test_login_sets_the_refresh_cookie(client: AsyncClient, user: User) -> None:
    response = await _login(client)

    header = _set_cookie_header(response)
    attributes = {part.strip().split("=")[0].lower(): part for part in header.split(";")[1:]}
    assert "httponly" in attributes
    assert "secure" in attributes
    assert attributes["samesite"].strip().lower() == "samesite=strict"
    assert attributes["path"].strip() == "Path=/api/v1/session"
    assert attributes["max-age"].strip() == f"Max-Age={settings.refresh_token_days * 86400}"
    assert "domain" not in attributes
    assert set(response.json()) == {"access_token", "token_type"}


async def test_cookie_is_not_secure_when_disabled(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "refresh_cookie_secure", False)

    response = await _login(client)

    assert "secure" not in _set_cookie_header(response).lower()


async def test_only_the_hash_is_stored(client: AsyncClient, session: AsyncSession, user: User) -> None:
    raw = _cookie(await _login(client))

    stored = (await session.execute(select(RefreshToken.token_hash))).scalars().all()

    assert stored == [refresh_token_service._hash(raw)]
    assert raw not in stored


async def test_refresh_returns_a_working_token_and_a_new_cookie(client: AsyncClient, user: User) -> None:
    raw = _cookie(await _login(client))

    response = await _refresh(client, raw)

    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "bearer"
    assert await _me_status(client, response.json()["access_token"]) == 200
    new_raw = _cookie(response)
    assert new_raw != raw
    assert (await _refresh(client, new_raw)).status_code == 200


async def test_jar_sends_the_cookie_to_refresh(client: AsyncClient, user: User) -> None:
    # The cookie's Path and Secure attributes let a real client send it back on its own
    await _login(client)

    response = await client.post("/api/v1/session/refresh")

    assert response.status_code == 200, response.text


async def test_rotated_token_works_within_the_grace_window(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _cookie(await _login(client))
    first = await _refresh(client, raw)
    assert first.status_code == 200

    _shift_clock(monkeypatch, timedelta(seconds=settings.refresh_rotation_grace_seconds - 5))
    second = await _refresh(client, raw)

    assert second.status_code == 200, second.text
    assert _cookie(second) not in (raw, _cookie(first))


async def test_rotated_token_fails_after_the_grace_window(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _cookie(await _login(client))
    successor = _cookie(await _refresh(client, raw))

    _shift_clock(monkeypatch, timedelta(seconds=settings.refresh_rotation_grace_seconds + 5))
    response = await _refresh(client, raw)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired session"}
    _assert_cleared(response)
    # The successor isn't touched
    assert (await _refresh(client, successor)).status_code == 200


async def test_grace_window_counts_from_the_first_rotation(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    grace = settings.refresh_rotation_grace_seconds
    raw = _cookie(await _login(client))
    assert (await _refresh(client, raw)).status_code == 200
    _shift_clock(monkeypatch, timedelta(seconds=grace - 5))
    assert (await _refresh(client, raw)).status_code == 200

    _shift_clock(monkeypatch, timedelta(seconds=grace + 5))

    assert (await _refresh(client, raw)).status_code == 401


async def test_successor_lifetime_slides(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    days = settings.refresh_token_days
    raw = _cookie(await _login(client))
    _shift_clock(monkeypatch, timedelta(days=days - 1))
    successor = _cookie(await _refresh(client, raw))

    _shift_clock(monkeypatch, timedelta(days=days + 1))

    assert (await _refresh(client, raw)).status_code == 401
    assert (await _refresh(client, successor)).status_code == 200


@pytest.mark.parametrize("case", ["expired", "revoked", "unknown", "missing"])
async def test_invalid_cookie_is_rejected_and_cleared(
    client: AsyncClient, session: AsyncSession, user: User, case: str
) -> None:
    raw: str | None = _cookie(await _login(client))
    if case == "expired":
        await session.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    elif case == "revoked":
        await session.execute(update(RefreshToken).values(revoked_at=datetime.now(UTC)))
        await session.commit()
    elif case == "unknown":
        raw = "not-a-refresh-token"
    else:
        raw = None

    response = await _refresh(client, raw)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired session"}
    _assert_cleared(response)


async def test_blocked_user_is_refused_but_keeps_the_token(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    raw = _cookie(await _login(client))
    admin = await _make_active_user(session, "admin@example.com", "admin")
    admin.role = UserRole.ADMIN
    session.add(admin)
    await session.commit()
    admin_headers = {"Authorization": f"Bearer {create_access_token(admin)}"}
    suspend = await client.patch(f"/api/v1/admin/users/{user.id}/suspend", headers=admin_headers)
    assert suspend.status_code == 200, suspend.text

    blocked = await _refresh(client, raw)

    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "Account suspended"}
    assert "refresh_token=" not in " ".join(blocked.headers.get_list("set-cookie"))

    approve = await client.patch(f"/api/v1/admin/users/{user.id}/approve", headers=admin_headers)
    assert approve.status_code == 200, approve.text
    assert (await _refresh(client, raw)).status_code == 200


async def test_logout_revokes_the_token(client: AsyncClient, user: User) -> None:
    raw = _cookie(await _login(client))
    client.cookies.clear()

    response = await client.post("/api/v1/session/logout", headers={"Cookie": f"refresh_token={raw}"})

    assert response.status_code == 204
    _assert_cleared(response)
    assert (await _refresh(client, raw)).status_code == 401


async def test_logout_leaves_other_sessions_alone(client: AsyncClient, user: User) -> None:
    other_device = _cookie(await _login(client))
    this_device = _cookie(await _login(client))
    client.cookies.clear()

    await client.post("/api/v1/session/logout", headers={"Cookie": f"refresh_token={this_device}"})

    assert (await _refresh(client, other_device)).status_code == 200


@pytest.mark.parametrize("cookie", [None, "not-a-refresh-token"])
async def test_logout_always_succeeds(client: AsyncClient, cookie: str | None) -> None:
    headers = {"Cookie": f"refresh_token={cookie}"} if cookie else {}

    response = await client.post("/api/v1/session/logout", headers=headers)

    assert response.status_code == 204
    _assert_cleared(response)


async def test_change_password_revokes_other_refresh_tokens(client: AsyncClient, user: User) -> None:
    other_device = _cookie(await _login(client))
    login = await _login(client)
    this_device = _cookie(login)

    response = await client.post(
        "/api/v1/users/me/password",
        json={"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200, response.text
    new_raw = _cookie(response)
    assert (await _refresh(client, other_device)).status_code == 401
    assert (await _refresh(client, this_device)).status_code == 401
    assert (await _refresh(client, new_raw)).status_code == 200


async def test_stale_token_version_is_rejected_and_cleared(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    # A refresh that raced a password change can insert a successor after revoke_all ran. It isn't revoked,
    # but it carries the old token_version, so it must still fail.
    raw = _cookie(await _login(client))
    user.token_version += 1
    session.add(user)
    await session.commit()

    response = await _refresh(client, raw)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired session"}
    _assert_cleared(response)


async def test_stale_token_version_gets_401_even_when_blocked(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    raw = _cookie(await _login(client))
    user.token_version += 1
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    response = await _refresh(client, raw)

    assert response.status_code == 401
    _assert_cleared(response)


async def test_password_change_cookie_carries_the_new_token_version(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    login = await _login(client)

    response = await client.post(
        "/api/v1/users/me/password",
        json={"current_password": _PASSWORD, "new_password": _NEW_PASSWORD},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200, response.text
    new_raw = _cookie(response)
    stored = await session.execute(
        select(RefreshToken.token_version).where(
            col(RefreshToken.token_hash) == refresh_token_service._hash(new_raw)
        )
    )
    await session.refresh(user)
    assert stored.scalar_one() == user.token_version == 1
    assert (await _refresh(client, new_raw)).status_code == 200


async def test_failed_change_password_keeps_refresh_tokens(client: AsyncClient, user: User) -> None:
    login = await _login(client)
    raw = _cookie(login)

    response = await client.post(
        "/api/v1/users/me/password",
        json={"current_password": "not-the-password", "new_password": _NEW_PASSWORD},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 400
    assert (await _refresh(client, raw)).status_code == 200


async def test_password_reset_revokes_all_refresh_tokens(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    first = _cookie(await _login(client))
    second = _cookie(await _login(client))
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": user.email})).status_code == 202
    [line] = [line for line in outbox[-1]["text"].splitlines() if line.startswith(_RESET_PREFIX)]

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": line.removeprefix(_RESET_PREFIX), "password": _NEW_PASSWORD},
    )

    assert response.status_code == 204
    assert (await _refresh(client, first)).status_code == 401
    assert (await _refresh(client, second)).status_code == 401


async def test_deleting_a_user_removes_their_refresh_tokens(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    raw = _cookie(await _login(client))
    admin = await _make_active_user(session, "admin@example.com", "admin")
    admin.role = UserRole.ADMIN
    session.add(admin)
    await session.commit()

    response = await client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {create_access_token(admin)}"},
    )

    assert response.status_code == 204, response.text
    remaining = await session.execute(select(RefreshToken).where(col(RefreshToken.user_id) == user.id))
    assert remaining.scalars().all() == []
    assert (await _refresh(client, raw)).status_code == 401


@pytest.mark.parametrize("minutes", [15, 5])
async def test_access_token_lifetime_follows_the_setting(
    client: AsyncClient, user: User, monkeypatch: pytest.MonkeyPatch, minutes: int
) -> None:
    monkeypatch.setattr(settings, "jwt_expire_minutes", minutes)
    raw = _cookie(await _login(client))

    response = await _refresh(client, raw)

    payload = jwt.decode(
        response.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["exp"] - payload["iat"] == minutes * 60


def test_access_tokens_default_to_15_minutes() -> None:
    assert type(settings).model_fields["jwt_expire_minutes"].default == 15

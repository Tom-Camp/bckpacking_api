from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import create_access_token
from app.models.user import User
from app.services import email as email_service
from app.utils.config import settings
from tests.api.conftest import _PASSWORD

_NEW_PASSWORD = "Ziv8%quartz-Lantern!muskeg"  # nosec B105
_PREFIX = "https://ui.example/reset-password#"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    async def _send(to: str, subject: str, text: str, html: str) -> None:
        sent.append(text)

    monkeypatch.setattr(email_service, "send_email", _send)
    monkeypatch.setattr(settings, "app_base_url", "https://ui.example")
    return sent


async def _reset_token(client: AsyncClient, outbox: list[str], email: str) -> str:
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": email})).status_code == 202
    [line] = [line for line in outbox[-1].splitlines() if line.startswith(_PREFIX)]
    return line.removeprefix(_PREFIX)


async def _me_status(client: AsyncClient, token: str) -> int:
    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    return response.status_code


async def _login(client: AsyncClient, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "hiker@example.com", "password": password}
    )
    assert response.status_code == 200
    token: str = response.json()["access_token"]
    return token


async def _change_password(client: AsyncClient, token: str, current: str, new: str) -> Any:
    return await client.post(
        "/api/v1/users/me/password",
        json={"current_password": current, "new_password": new},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_reset_revokes_earlier_tokens(client: AsyncClient, user: User, outbox: list[str]) -> None:
    before = await _login(client, _PASSWORD)
    reset = await _reset_token(client, outbox, user.email)

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": reset, "password": _NEW_PASSWORD}
    )

    assert response.status_code == 204
    assert await _me_status(client, before) == 401
    assert await _me_status(client, await _login(client, _NEW_PASSWORD)) == 200


async def test_revoked_token_gets_the_expired_token_response(
    client: AsyncClient, user: User, outbox: list[str]
) -> None:
    before = await _login(client, _PASSWORD)
    reset = await _reset_token(client, outbox, user.email)
    await client.post("/api/v1/auth/reset-password", json={"token": reset, "password": _NEW_PASSWORD})

    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {before}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("case", ["bad_token", "weak_password"])
async def test_failed_reset_keeps_tokens(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[str], case: str
) -> None:
    before = await _login(client, _PASSWORD)
    reset = await _reset_token(client, outbox, user.email)
    body = (
        {"token": "not-a-token", "password": _NEW_PASSWORD}
        if case == "bad_token"
        else {"token": reset, "password": "password1"}
    )

    response = await client.post("/api/v1/auth/reset-password", json=body)

    assert response.status_code == (400 if case == "bad_token" else 422)
    await session.refresh(user)
    assert user.token_version == 0
    assert await _me_status(client, before) == 200


async def test_change_password_returns_a_working_token_and_revokes_the_others(
    client: AsyncClient, user: User
) -> None:
    other_device = await _login(client, _PASSWORD)
    this_device = await _login(client, _PASSWORD)

    response = await _change_password(client, this_device, _PASSWORD, _NEW_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert await _me_status(client, body["access_token"]) == 200
    assert await _me_status(client, this_device) == 401
    assert await _me_status(client, other_device) == 401


@pytest.mark.parametrize(
    ("current", "new", "status"), [("not-the-password", _NEW_PASSWORD, 400), (_PASSWORD, "password1", 422)]
)
async def test_failed_change_password_keeps_tokens(
    client: AsyncClient, session: AsyncSession, user: User, current: str, new: str, status: int
) -> None:
    token = create_access_token(user)

    response = await _change_password(client, token, current, new)

    assert response.status_code == status
    await session.refresh(user)
    assert user.token_version == 0
    assert await _me_status(client, token) == 200

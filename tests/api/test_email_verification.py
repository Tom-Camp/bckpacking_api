from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.auth_token import AuthToken, TokenPurpose
from app.models.user import User, UserStatus
from app.services import auth_token
from app.services import email as email_service
from app.utils.config import settings
from tests.api.conftest import _PASSWORD

_NEW_PASSWORD = "Ziv8%quartz-Lantern!muskeg"  # nosec B105
_REGISTER = "/api/v1/auth/register"
_VERIFY = "/api/v1/auth/verify-email"
_RESEND = "/api/v1/auth/resend-verification"
_RESEND_MESSAGE = {"message": "If that account needs verifying, we've sent a new link."}
_INVALID = "This verification link is invalid or has expired"
_VERIFY_PREFIX = "https://ui.example/verify-email#"
_RESET_PREFIX = "https://ui.example/reset-password#"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    async def _send(to: str, subject: str, text: str, html: str) -> None:
        sent.append({"to": to, "subject": subject, "text": text, "html": html})

    monkeypatch.setattr(email_service, "send_email", _send)
    monkeypatch.setattr(settings, "app_base_url", "https://ui.example")
    return sent


def _token_from(message: dict[str, str], prefix: str = _VERIFY_PREFIX) -> str:
    [line] = [line for line in message["text"].splitlines() if line.startswith(prefix)]
    return line.removeprefix(prefix)


async def _register(client: AsyncClient, email: str = "new@example.com") -> int:
    response = await client.post(
        _REGISTER, json={"email": email, "password": _PASSWORD, "username": "newbie"}
    )
    return response.status_code


async def _new_user(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.username == "newbie"))
    user = result.scalar_one()
    await session.refresh(user)
    return user


async def _verify(client: AsyncClient, token: str) -> int:
    return (await client.post(_VERIFY, json={"token": token})).status_code


async def _make_old(session: AsyncSession) -> None:
    # Moves every token out of the resend cooldown
    await session.execute(update(AuthToken).values(created_at=datetime.now(UTC) - timedelta(minutes=5)))
    await session.commit()


async def test_register_sends_a_verification_link(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    response = await client.post(
        _REGISTER, json={"email": "New@Example.com", "password": _PASSWORD, "username": "newbie"}
    )

    assert response.status_code == 201
    assert response.json() == {
        "message": "Registration successful. Check your email to verify your account."
    }
    [message] = outbox
    assert message["to"] == "new@example.com"
    assert _token_from(message)
    assert _VERIFY_PREFIX in message["html"]
    assert (await _new_user(session)).email_verified_at is None


async def test_register_conflict_sends_nothing(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    assert await _register(client, user.email) == 409

    assert outbox == []


async def test_verify_sets_email_verified_at(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    await _register(client)

    assert await _verify(client, _token_from(outbox[0])) == 204

    user = await _new_user(session)
    assert user.email_verified_at is not None
    login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": _PASSWORD})
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.json()["email_verified_at"] is not None


async def test_verifying_twice_succeeds_and_keeps_the_first_timestamp(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    await _register(client)
    token = _token_from(outbox[0])
    assert await _verify(client, token) == 204
    first = (await _new_user(session)).email_verified_at

    assert await _verify(client, token) == 204

    assert (await _new_user(session)).email_verified_at == first


async def test_expired_token_is_rejected(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    await _register(client)
    await session.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await session.commit()

    response = await client.post(_VERIFY, json={"token": _token_from(outbox[0])})

    assert response.status_code == 400
    assert response.json()["detail"] == _INVALID
    assert (await _new_user(session)).email_verified_at is None


async def test_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.post(_VERIFY, json={"token": "not-a-token"})

    assert response.status_code == 400
    assert response.json()["detail"] == _INVALID


async def test_reset_token_cannot_verify(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    await client.post("/api/v1/auth/forgot-password", json={"email": user.email})

    assert await _verify(client, _token_from(outbox[0], _RESET_PREFIX)) == 400
    await session.refresh(user)
    assert user.email_verified_at is None


async def test_verify_token_cannot_reset(client: AsyncClient, outbox: list[dict[str, str]]) -> None:
    await _register(client)

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": _token_from(outbox[0]), "password": _NEW_PASSWORD}
    )

    assert response.status_code == 400


async def test_resend_sends_a_new_link_and_the_old_one_stops_working(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    await _register(client)
    old = _token_from(outbox[0])
    await _make_old(session)

    response = await client.post(_RESEND, json={"email": "NEW@example.com"})

    assert response.status_code == 202
    assert response.json() == _RESEND_MESSAGE
    assert len(outbox) == 2
    new = _token_from(outbox[1])
    assert await _verify(client, old) == 400
    assert await _verify(client, new) == 204


async def test_resend_within_cooldown_sends_nothing(
    client: AsyncClient, outbox: list[dict[str, str]]
) -> None:
    await _register(client)

    response = await client.post(_RESEND, json={"email": "new@example.com"})

    assert response.status_code == 202
    assert response.json() == _RESEND_MESSAGE
    assert len(outbox) == 1


async def test_resend_for_a_verified_user_sends_nothing(
    client: AsyncClient, session: AsyncSession, outbox: list[dict[str, str]]
) -> None:
    await _register(client)
    assert await _verify(client, _token_from(outbox[0])) == 204
    await _make_old(session)

    response = await client.post(_RESEND, json={"email": "new@example.com"})

    assert response.status_code == 202
    assert response.json() == _RESEND_MESSAGE
    assert len(outbox) == 1


async def test_resend_for_an_unknown_email_sends_nothing(
    client: AsyncClient, outbox: list[dict[str, str]]
) -> None:
    response = await client.post(_RESEND, json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert response.json() == _RESEND_MESSAGE
    assert outbox == []


async def test_resend_for_a_blocked_user_sends_nothing(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    response = await client.post(_RESEND, json={"email": user.email})

    assert response.status_code == 202
    assert response.json() == _RESEND_MESSAGE
    assert outbox == []


async def test_password_reset_verifies_the_email(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    assert user.email_verified_at is None
    await client.post("/api/v1/auth/forgot-password", json={"email": user.email})

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": _token_from(outbox[0], _RESET_PREFIX), "password": _NEW_PASSWORD},
    )

    assert response.status_code == 204
    await session.refresh(user)
    assert user.email_verified_at is not None


async def test_superseded_token_still_succeeds_once_verified(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    # An older link followed after the address was verified through a newer one: nothing to report
    old = await auth_token.issue(session, user, TokenPurpose.VERIFY_EMAIL, timedelta(hours=24))
    new = await auth_token.issue(session, user, TokenPurpose.VERIFY_EMAIL, timedelta(hours=24))
    await session.commit()
    assert await _verify(client, new) == 204

    assert await _verify(client, old) == 204


async def test_unverified_user_can_still_log_in(client: AsyncClient, outbox: list[dict[str, str]]) -> None:
    # Guards the rollout: login doesn't require verification until #92, after the UI can verify (UI #94)
    await _register(client)

    response = await client.post(
        "/api/v1/auth/login", json={"email": "new@example.com", "password": _PASSWORD}
    )

    assert response.status_code == 200

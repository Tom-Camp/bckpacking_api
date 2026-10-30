import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.auth_token import AuthToken
from app.models.user import User, UserStatus
from app.services import email as email_service
from app.utils.config import settings
from tests.api.conftest import _PASSWORD

_NEW_PASSWORD = "Ziv8%quartz-Lantern!muskeg"  # nosec B105
_FORGOT = "/api/v1/auth/forgot-password"
_RESET = "/api/v1/auth/reset-password"
_MESSAGE = {"message": "If an account exists for that email, we've sent a reset link."}
_INVALID = "This reset link is invalid or has expired"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    async def _send(to: str, subject: str, text: str, html: str) -> None:
        sent.append({"to": to, "subject": subject, "text": text, "html": html})

    monkeypatch.setattr(email_service, "send_email", _send)
    monkeypatch.setattr(settings, "app_base_url", "https://ui.example")
    return sent


def _token_from(message: dict[str, str]) -> str:
    prefix = "https://ui.example/reset-password#"
    [line] = [line for line in message["text"].splitlines() if line.startswith(prefix)]
    return line.removeprefix(prefix)


async def _request_token(client: AsyncClient, outbox: list[dict[str, str]], email: str) -> str:
    response = await client.post(_FORGOT, json={"email": email})
    assert response.status_code == 202
    return _token_from(outbox[-1])


async def _login_status(client: AsyncClient, password: str) -> int:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "hiker@example.com", "password": password}
    )
    return response.status_code


async def test_forgot_password_emails_a_link_to_an_existing_user(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    response = await client.post(_FORGOT, json={"email": user.email})

    assert response.status_code == 202
    assert response.json() == _MESSAGE
    [message] = outbox
    assert message["to"] == user.email
    assert "https://ui.example/reset-password#" in message["text"]
    assert "https://ui.example/reset-password#" in message["html"]
    assert _token_from(message)


async def test_forgot_password_for_unknown_email_answers_the_same_and_sends_nothing(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    response = await client.post(_FORGOT, json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert response.json() == _MESSAGE
    assert outbox == []


async def test_forgot_password_sends_nothing_to_a_blocked_user(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    response = await client.post(_FORGOT, json={"email": user.email})

    assert response.status_code == 202
    assert response.json() == _MESSAGE
    assert outbox == []


async def test_second_request_within_cooldown_sends_nothing(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    for _ in range(2):
        response = await client.post(_FORGOT, json={"email": user.email})
        assert response.status_code == 202
        assert response.json() == _MESSAGE

    assert len(outbox) == 1


async def test_request_after_cooldown_sends_again(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    await _request_token(client, outbox, user.email)
    await session.execute(update(AuthToken).values(created_at=datetime.now(UTC) - timedelta(seconds=61)))
    await session.commit()

    await _request_token(client, outbox, user.email)

    assert len(outbox) == 2


async def test_forgot_password_matches_mixed_case_email(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    response = await client.post(_FORGOT, json={"email": "Hiker@EXAMPLE.com"})

    assert response.status_code == 202
    assert [m["to"] for m in outbox] == [user.email]


async def test_reset_sets_the_new_password(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)

    response = await client.post(_RESET, json={"token": token, "password": _NEW_PASSWORD})

    assert response.status_code == 204
    assert await _login_status(client, _NEW_PASSWORD) == 200
    assert await _login_status(client, _PASSWORD) == 401


async def test_reset_token_works_only_once(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)
    assert (await client.post(_RESET, json={"token": token, "password": _NEW_PASSWORD})).status_code == 204

    response = await client.post(_RESET, json={"token": token, "password": _PASSWORD})

    assert response.status_code == 400
    assert response.json()["detail"] == _INVALID
    assert await _login_status(client, _NEW_PASSWORD) == 200


async def test_expired_token_is_rejected(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)
    await session.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await session.commit()

    response = await client.post(_RESET, json={"token": token, "password": _NEW_PASSWORD})

    assert response.status_code == 400
    assert response.json()["detail"] == _INVALID


async def test_garbage_token_is_rejected(client: AsyncClient, user: User) -> None:
    response = await client.post(_RESET, json={"token": "not-a-token", "password": _NEW_PASSWORD})

    assert response.status_code == 400
    assert response.json()["detail"] == _INVALID


async def test_weak_password_is_rejected_and_the_token_still_works(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)

    response = await client.post(_RESET, json={"token": token, "password": "password1"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert (await client.post(_RESET, json={"token": token, "password": _NEW_PASSWORD})).status_code == 204


async def test_new_token_invalidates_the_earlier_one(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    first = await _request_token(client, outbox, user.email)
    await session.execute(update(AuthToken).values(created_at=datetime.now(UTC) - timedelta(minutes=5)))
    await session.commit()
    second = await _request_token(client, outbox, user.email)

    assert (await client.post(_RESET, json={"token": first, "password": _NEW_PASSWORD})).status_code == 400
    assert (await client.post(_RESET, json={"token": second, "password": _NEW_PASSWORD})).status_code == 204


async def test_token_for_another_purpose_cannot_reset(
    client: AsyncClient, session: AsyncSession, user: User
) -> None:
    # Inserted with SQL: the enum has no other member yet (#91 adds verify_email)
    raw = "verify-token"
    await session.execute(
        insert(AuthToken).values(
            id=uuid4(),
            user_id=user.id,
            purpose="verify_email",
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await session.commit()

    response = await client.post(_RESET, json={"token": raw, "password": _NEW_PASSWORD})

    assert response.status_code == 400


async def test_reset_is_refused_for_a_blocked_user(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    response = await client.post(_RESET, json={"token": token, "password": _NEW_PASSWORD})

    assert response.status_code == 400


async def test_only_the_token_hash_is_stored(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)

    [stored] = (await session.execute(select(AuthToken))).scalars().all()

    assert stored.token_hash != token
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()


async def test_reset_token_is_not_a_bearer_token(
    client: AsyncClient, user: User, outbox: list[dict[str, str]]
) -> None:
    token = await _request_token(client, outbox, user.email)

    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_deleting_a_user_deletes_their_tokens(
    client: AsyncClient, session: AsyncSession, user: User, outbox: list[dict[str, str]]
) -> None:
    await _request_token(client, outbox, user.email)

    await session.delete(user)
    await session.commit()

    remaining = await session.execute(select(AuthToken).where(col(AuthToken.user_id) == user.id))
    assert remaining.scalars().all() == []

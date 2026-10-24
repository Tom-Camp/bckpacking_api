import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus
from app.services import user as user_service
from tests.api.conftest import _PASSWORD

_NEW_PASSWORD = "Vq8#tLm2!pWz9&kRb4^nHs7Xe"  # nosec B105


async def test_update_me_sets_picture_and_body_weight(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.patch(
        "/api/v1/users/me",
        json={"picture": "https://example.com/hiker.png", "body_weight_g": 72500},
        headers=auth_headers,
    )

    assert response.status_code == 200
    me = (await client.get("/api/v1/users/me", headers=auth_headers)).json()
    assert me["picture"] == "https://example.com/hiker.png"
    assert me["body_weight_g"] == 72500


async def test_update_me_rejects_non_positive_body_weight(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for weight in (0, -1):
        response = await client.patch(
            "/api/v1/users/me", json={"body_weight_g": weight}, headers=auth_headers
        )

        assert response.status_code == 422


async def test_measurements_preference_defaults_to_imperial_and_can_change(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    me = (await client.get("/api/v1/users/me", headers=auth_headers)).json()
    assert me["measurements"] == "imperial"

    response = await client.patch("/api/v1/users/me", json={"measurements": "metric"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["measurements"] == "metric"


async def test_measurements_rejects_unknown_unit_system(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.patch(
        "/api/v1/users/me", json={"measurements": "furlongs"}, headers=auth_headers
    )

    assert response.status_code == 422


async def test_update_me_username_must_be_free(
    client: AsyncClient, auth_headers: dict[str, str], other_user: User
) -> None:
    taken = await client.patch(
        "/api/v1/users/me", json={"username": other_user.username}, headers=auth_headers
    )
    free = await client.patch("/api/v1/users/me", json={"username": "trail-name"}, headers=auth_headers)

    assert taken.status_code == 409
    assert taken.json()["detail"] == "Username already taken"
    assert free.status_code == 200
    assert free.json()["username"] == "trail-name"


async def _change_password(
    client: AsyncClient, headers: dict[str, str], current: str, new: str
) -> tuple[int, dict[str, object] | None]:
    response = await client.post(
        "/api/v1/users/me/password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )
    return response.status_code, response.json() if response.content else None


async def _login_status(client: AsyncClient, email: str, password: str) -> int:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.status_code


async def test_change_password_replaces_the_login_password(
    client: AsyncClient, user: User, auth_headers: dict[str, str]
) -> None:
    status, body = await _change_password(client, auth_headers, _PASSWORD, _NEW_PASSWORD)

    assert status == 204
    assert body is None
    assert await _login_status(client, user.email, _NEW_PASSWORD) == 200
    assert await _login_status(client, user.email, _PASSWORD) == 401


async def test_change_password_rejects_wrong_current_password_with_400(
    client: AsyncClient, user: User, auth_headers: dict[str, str]
) -> None:
    old_hash = user.password_hash

    status, body = await _change_password(client, auth_headers, "not-the-password", _NEW_PASSWORD)

    # Not 401: the UI treats any 401 as an expired session.
    assert status == 400
    assert body == {"detail": "Current password is incorrect"}
    assert user.password_hash == old_hash


async def test_change_password_rejects_weak_new_password(
    client: AsyncClient, user: User, auth_headers: dict[str, str]
) -> None:
    old_hash = user.password_hash

    response = await client.post(
        "/api/v1/users/me/password",
        json={"current_password": _PASSWORD, "new_password": "password1"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.content == (
        b'{"detail":[{"type":"value_error","loc":["body","new_password"],'
        b'"msg":"Value error, This is a very common password.","input":"password1","ctx":{"error":{}}}]}'
    )
    assert user.password_hash == old_hash


def _never_called(*_args: object) -> None:
    raise AssertionError("zxcvbn must not run")


async def test_change_password_rejects_new_password_over_72_bytes_without_zxcvbn(
    client: AsyncClient, user: User, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user_service, "check_password_strength", _never_called)
    old_hash = user.password_hash

    status, body = await _change_password(client, auth_headers, _PASSWORD, _NEW_PASSWORD * 3)

    assert status == 422
    assert isinstance(body, dict)
    detail = body["detail"][0]  # type: ignore[index]
    assert detail["loc"] == ["body", "new_password"]
    assert detail["msg"] == "Value error, Password must be at most 72 bytes"
    assert user.password_hash == old_hash


async def test_change_password_needs_a_token(client: AsyncClient) -> None:
    status, _ = await _change_password(client, {}, _PASSWORD, _NEW_PASSWORD)

    assert status == 401


async def test_blocked_user_cannot_change_password(
    client: AsyncClient, session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()
    old_hash = user.password_hash

    status, body = await _change_password(client, auth_headers, _PASSWORD, _NEW_PASSWORD)

    assert status == 403
    assert body == {"detail": "Account suspended"}
    assert user.password_hash == old_hash

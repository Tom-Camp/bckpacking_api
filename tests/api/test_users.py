from httpx import AsyncClient

from app.models.user import User


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

from httpx import AsyncClient

from app.schemas.user import UserPublic


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


def test_body_weight_is_not_in_public_profile() -> None:
    assert "body_weight_g" not in UserPublic.model_fields

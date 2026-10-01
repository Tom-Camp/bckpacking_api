import uuid
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.middleware import redact_path
from app.models.user import User, UserStatus

TRIP_PAYLOAD = {"name": "Wonderland Trail", "emergency_contact": "Jo, 555-0100"}


async def _create_trip(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.post("/api/v1/trips", json=TRIP_PAYLOAD, headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def _share(client: AsyncClient, trip_id: str, headers: dict[str, str]) -> str:
    response = await client.post(f"/api/v1/trips/{trip_id}/share", headers=headers)
    assert response.status_code == 200
    return cast(str, response.json()["share_token"])


async def test_share_is_idempotent_and_shown_to_owner(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    assert trip["share_token"] is None

    token = await _share(client, trip["id"], auth_headers)

    assert len(token) >= 40
    assert await _share(client, trip["id"], auth_headers) == token
    response = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert response.json()["share_token"] == token


async def test_shared_trip_is_public_and_omits_private_fields(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    item = await client.post(
        "/api/v1/gear",
        json={"name": "Tent", "category": "shelter", "notes": "seam leaks"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/trips/{trip['id']}/gear", json={"gear_item_id": item.json()["id"]}, headers=auth_headers
    )
    await client.post(
        f"/api/v1/trips/{trip['id']}/notes", json={"content": "spare key"}, headers=auth_headers
    )
    token = await _share(client, trip["id"], auth_headers)

    response = await client.get(f"/api/v1/shared/trips/{token}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    body = response.json()
    assert body["name"] == "Wonderland Trail"
    assert body["owner"] == {"username": "hiker"}
    assert len(body["checklist_items"]) == 9
    assert body["food_plan"] is not None
    for private in ("user_id", "emergency_contact", "notes", "share_token"):
        assert private not in body
    [gear] = body["gear_list"]
    assert gear["gear_item"] == {"name": "Tent", "category": "shelter", "weight_g": 0.0, "kind": "base"}


async def test_unknown_token_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/shared/trips/not-a-real-token")
    assert response.status_code == 404


async def test_revoked_token_404_and_reshare_issues_new_token(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    token = await _share(client, trip["id"], auth_headers)

    response = await client.delete(f"/api/v1/trips/{trip['id']}/share", headers=auth_headers)

    assert response.status_code == 204
    assert (await client.get(f"/api/v1/shared/trips/{token}")).status_code == 404
    new_token = await _share(client, trip["id"], auth_headers)
    assert new_token != token
    assert (await client.get(f"/api/v1/shared/trips/{new_token}")).status_code == 200


async def test_blocked_owners_share_link_404(
    client: AsyncClient, session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    token = await _share(client, trip["id"], auth_headers)

    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    assert (await client.get(f"/api/v1/shared/trips/{token}")).status_code == 404


@pytest.mark.parametrize("method", ["post", "delete"])
async def test_non_owner_cannot_change_sharing(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str], method: str
) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.request(
        method.upper(), f"/api/v1/trips/{trip['id']}/share", headers=other_auth_headers
    )

    assert response.status_code == 403


async def test_sharing_requires_auth(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)
    response = await client.post(f"/api/v1/trips/{trip['id']}/share")
    assert response.status_code == 401


_ANY_ID = str(uuid.uuid4())
_WRITE_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("PATCH", "", {"name": "Hijacked"}),
    ("DELETE", "", None),
    ("POST", "/share", None),
    ("DELETE", "/share", None),
    ("POST", "/gear", {"gear_item_id": _ANY_ID}),
    ("POST", f"/gear/copy-from/{_ANY_ID}", None),
    ("PATCH", f"/gear/{_ANY_ID}", {"packed": True}),
    ("DELETE", f"/gear/{_ANY_ID}", None),
    ("POST", "/notes", {"content": "hi"}),
    ("PATCH", f"/notes/{_ANY_ID}", {"content": "hi"}),
    ("DELETE", f"/notes/{_ANY_ID}", None),
    ("PATCH", "/checklist/permit", {"status": "done"}),
    ("PATCH", "/food-plan", {"target_kcal_per_day": 1}),
    ("POST", "/food-plan/items", {"day": 1, "name": "Oats", "weight_g": 100, "kcal": 400}),
    ("PATCH", f"/food-plan/items/{_ANY_ID}", {"name": "Oats"}),
    ("DELETE", f"/food-plan/items/{_ANY_ID}", None),
]


@pytest.mark.parametrize(("method", "suffix", "body"), _WRITE_ROUTES)
async def test_authenticated_non_owner_cannot_edit_shared_trip(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    method: str,
    suffix: str,
    body: dict[str, Any] | None,
) -> None:
    trip = await _create_trip(client, auth_headers)
    await _share(client, trip["id"], auth_headers)

    response = await client.request(
        method, f"/api/v1/trips/{trip['id']}{suffix}", json=body, headers=other_auth_headers
    )

    assert response.status_code == 403


def _routes(prefix: str) -> set[tuple[str, str]]:
    # From the OpenAPI schema: app.routes nests included routers rather than listing their routes.
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(prefix)
        for method in operations
    }


def test_every_trip_write_route_is_covered_by_the_non_owner_test() -> None:
    write_routes = {r for r in _routes("/api/v1/trips/{trip_id}") if r[0] != "GET"}
    assert len(write_routes) == len(_WRITE_ROUTES)


def test_shared_routes_are_read_only() -> None:
    shared = _routes("/api/v1/shared")
    assert shared
    assert {method for method, _ in shared} == {"GET"}


def test_share_token_is_redacted_from_logged_paths() -> None:
    assert redact_path("/api/v1/shared/trips/s3cr3t") == "/api/v1/shared/trips/<redacted>"
    assert redact_path("/api/v1/trips/abc") == "/api/v1/trips/abc"

import uuid
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.main import app
from app.middleware import redact_path
from app.models.trip import Trip
from app.models.user import User, UserStatus
from app.services import trip as trip_service

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


async def test_enable_sharing_keeps_a_token_set_behind_a_stale_trip(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    # Simulates losing the race: another request stored a token after this one loaded the trip.
    trip_id = uuid.UUID((await _create_trip(client, auth_headers))["id"])
    trip = await session.get(Trip, trip_id)
    assert trip is not None and trip.share_token is None
    existing = "token-from-the-other-request"
    table = Trip.__table__  # type: ignore[attr-defined]
    await session.execute(update(table).where(table.c.id == trip_id).values(share_token=existing))
    await session.commit()

    token = await trip_service.enable_sharing(session, trip)

    assert token == existing
    assert trip.share_token == existing
    stored = (await session.execute(select(Trip.share_token).where(col(Trip.id) == trip_id))).scalar_one()
    assert stored == existing


CORE_KEYS = {
    "name",
    "description",
    "area",
    "trip_type",
    "start_date",
    "end_date",
    "start_trailhead",
    "end_trailhead",
    "total_distance_m",
    "elevation_gain_m",
    "water_carry_l",
    "map_link",
    "owner",
}
SECTION_KEYS = {"gear_list", "food_plan", "checklist_items", "checklist_ready", "emergency_contact"}
SHARE_FLAGS = ("share_gear", "share_food", "share_checklist", "share_emergency_contact")
# The sections each toggle exposes (checklist_ready follows the checklist toggle).
SECTIONS_BY_FLAG = {
    "share_gear": {"gear_list"},
    "share_food": {"food_plan"},
    "share_checklist": {"checklist_items", "checklist_ready"},
    "share_emergency_contact": {"emergency_contact"},
}


async def _set_flags(client: AsyncClient, trip_id: str, headers: dict[str, str], **flags: bool) -> None:
    response = await client.patch(f"/api/v1/trips/{trip_id}", json=flags, headers=headers)
    assert response.status_code == 200


async def _shared_trip_with_everything(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    """A shared trip with a gear line, a food item and a note; returns (trip id, token). All toggles off."""
    trip = await _create_trip(client, headers)
    item = await client.post(
        "/api/v1/gear",
        json={"name": "Tent", "category": "shelter", "notes": "seam leaks"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/trips/{trip['id']}/gear", json={"gear_item_id": item.json()["id"]}, headers=headers
    )
    await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": 1, "name": "Oats", "weight_g": 100, "kcal": 400},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/trips/{trip['id']}/checklist/permit",
        json={"status": "done", "details": "permit #12345"},
        headers=headers,
    )
    await client.post(f"/api/v1/trips/{trip['id']}/notes", json={"content": "spare key"}, headers=headers)
    return trip["id"], await _share(client, trip["id"], headers)


async def _get_shared(client: AsyncClient, token: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/shared/trips/{token}")
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


async def test_shared_trip_with_toggles_off_shows_only_core_details(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, token = await _shared_trip_with_everything(client, auth_headers)

    response = await client.get(f"/api/v1/shared/trips/{token}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    body = response.json()
    assert set(body) == CORE_KEYS | SECTION_KEYS
    assert {key: body[key] for key in SECTION_KEYS} == dict.fromkeys(SECTION_KEYS)
    assert body["name"] == "Wonderland Trail"
    assert body["owner"] == {"username": "hiker"}


async def test_shared_trip_with_toggles_on_exposes_only_allowlisted_fields(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip_id, token = await _shared_trip_with_everything(client, auth_headers)
    await _set_flags(client, trip_id, auth_headers, **dict.fromkeys(SHARE_FLAGS, True))

    body = await _get_shared(client, token)

    # Exact key sets at every level: a new field fails here until it's allowlisted on purpose.
    assert set(body) == CORE_KEYS | SECTION_KEYS
    assert body["owner"] == {"username": "hiker"}
    assert body["emergency_contact"] == "Jo, 555-0100"
    [gear] = body["gear_list"]
    assert set(gear) == {"gear_item", "quantity", "packed"}
    assert gear["gear_item"] == {
        "name": "Tent",
        "category": "shelter",
        "category_label": "Shelter",
        "weight_g": 0.0,
        "kind": "base",
    }
    assert len(body["checklist_items"]) == 9
    assert all(set(item) == {"item", "status"} for item in body["checklist_items"])
    assert {"item": "permit", "status": "done"} in body["checklist_items"]
    assert body["checklist_ready"] is False
    assert set(body["food_plan"]) == {"target_kcal_per_day", "target_food_g_per_day", "food"}
    [food] = body["food_plan"]["food"]
    assert food == {
        "day": 1,
        "name": "Oats",
        "meal_type": "breakfast",
        "servings": 1.0,
        "weight_g": 100.0,
        "kcal": 400,
    }


@pytest.mark.parametrize("flag", SHARE_FLAGS)
async def test_each_toggle_exposes_only_its_own_section(
    client: AsyncClient, auth_headers: dict[str, str], flag: str
) -> None:
    trip_id, token = await _shared_trip_with_everything(client, auth_headers)
    await _set_flags(client, trip_id, auth_headers, **{flag: True})

    body = await _get_shared(client, token)

    shown = {key for key in SECTION_KEYS if body[key] is not None}
    assert shown == SECTIONS_BY_FLAG[flag]


async def test_enabled_but_empty_sections_are_empty_lists(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    token = await _share(client, trip["id"], auth_headers)
    await _set_flags(client, trip["id"], auth_headers, share_gear=True, share_food=True)

    body = await _get_shared(client, token)

    assert body["gear_list"] == []
    assert body["food_plan"]["food"] == []


@pytest.mark.parametrize("flag", SHARE_FLAGS)
async def test_share_flag_rejects_null(client: AsyncClient, auth_headers: dict[str, str], flag: str) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.patch(f"/api/v1/trips/{trip['id']}", json={flag: None}, headers=auth_headers)

    assert response.status_code == 422


async def test_owner_sees_flags_and_they_survive_unsharing(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    assert {flag: trip[flag] for flag in SHARE_FLAGS} == dict.fromkeys(SHARE_FLAGS, False)
    await _share(client, trip["id"], auth_headers)
    await _set_flags(client, trip["id"], auth_headers, share_gear=True, share_checklist=True)

    await client.delete(f"/api/v1/trips/{trip['id']}/share", headers=auth_headers)
    token = await _share(client, trip["id"], auth_headers)

    owner_view = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)).json()
    assert {flag: owner_view[flag] for flag in SHARE_FLAGS} == {
        "share_gear": True,
        "share_food": False,
        "share_checklist": True,
        "share_emergency_contact": False,
    }
    body = await _get_shared(client, token)
    assert body["gear_list"] == []
    assert body["food_plan"] is None


def test_shared_trip_section_keys_are_required_in_openapi() -> None:
    # Keeps the UI's generated type non-optional: "not shared" is null, never a missing key.
    schema = app.openapi()["components"]["schemas"]["SharedTripRead"]
    assert set(schema["required"]) == CORE_KEYS | SECTION_KEYS
    assert set(schema["properties"]) == CORE_KEYS | SECTION_KEYS


def test_trip_read_only_adds_share_flags() -> None:
    schema = app.openapi()["components"]["schemas"]["TripRead"]
    assert set(schema["properties"]) == {
        "id",
        "name",
        "description",
        "area",
        "trip_type",
        "start_date",
        "end_date",
        "start_trailhead",
        "end_trailhead",
        "total_distance_m",
        "elevation_gain_m",
        "water_carry_l",
        "map_link",
        "food_plan",
        "checklist_items",
        "checklist_ready",
        "created_at",
        "updated_at",
        "user_id",
        "emergency_contact",
        "gear_list",
        "notes",
        "share_token",
        *SHARE_FLAGS,
    }


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

"""PATCH semantics shared by every updatable resource.

- An omitted field is left unchanged.
- An explicit null clears a nullable field.
- An explicit null on a non-nullable field returns 422 and leaves the row unchanged.

A PATCH with an empty body is a no-op that returns the current state, so it's used to read
resources that have no GET endpoint of their own.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.test_trips import _create_trip

Headers = dict[str, str]


async def _trip(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers, end_trailhead="Mowich Lake")
    return f"/api/v1/trips/{trip['id']}"


async def _gear_item(client: AsyncClient, headers: Headers) -> str:
    response = await client.post(
        "/api/v1/gear",
        json={"name": "Tent", "category": "shelter", "weight_g": 1200, "notes": "Stakes in side pocket"},
        headers=headers,
    )
    assert response.status_code == 201
    return f"/api/v1/gear/{response.json()['id']}"


async def _trip_gear(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers)
    item = await client.post("/api/v1/gear", json={"name": "Tent", "category": "shelter"}, headers=headers)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/gear", json={"gear_item_id": item.json()["id"]}, headers=headers
    )
    assert response.status_code == 201
    return f"/api/v1/trips/{trip['id']}/gear/{response.json()['id']}"


async def _note(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/notes", json={"content": "Bring extra socks."}, headers=headers
    )
    assert response.status_code == 201
    return f"/api/v1/trips/{trip['id']}/notes/{response.json()['id']}"


async def _checklist_item(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers)
    url = f"/api/v1/trips/{trip['id']}/checklist/water_sources"
    response = await client.patch(url, json={"details": "Two reliable springs"}, headers=headers)
    assert response.status_code == 200
    return url


async def _food_plan(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers)
    return f"/api/v1/trips/{trip['id']}/food-plan"


async def _food_item(client: AsyncClient, headers: Headers) -> str:
    trip = await _create_trip(client, headers)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": 1, "name": "Oatmeal", "weight_g": 100, "kcal": 400},
        headers=headers,
    )
    assert response.status_code == 201
    return f"/api/v1/trips/{trip['id']}/food-plan/items/{response.json()['id']}"


async def _me(client: AsyncClient, headers: Headers) -> str:
    response = await client.patch("/api/v1/users/me", json={"first_name": "Ada"}, headers=headers)
    assert response.status_code == 200
    return "/api/v1/users/me"


@dataclass(frozen=True)
class Case:
    id: str
    setup: Callable[[AsyncClient, Headers], Awaitable[str]]  # returns the PATCH url
    other_update: dict[str, Any]  # touches some field other than the ones checked
    non_nullable: str
    nullable: str | None = None  # populated by setup; None if the resource has no nullable fields


CASES = [
    Case("trip", _trip, {"description": "Clockwise"}, non_nullable="name", nullable="end_trailhead"),
    Case("gear-item", _gear_item, {"weight_g": 1100}, non_nullable="name", nullable="notes"),
    Case("trip-gear", _trip_gear, {"packed": True}, non_nullable="quantity"),
    Case("note", _note, {"content": "Bring more socks."}, non_nullable="content"),
    Case("checklist", _checklist_item, {"status": "done"}, non_nullable="status", nullable="details"),
    Case("food-plan", _food_plan, {"target_food_g_per_day": 900}, non_nullable="target_kcal_per_day"),
    Case("food-item", _food_item, {"kcal": 450}, non_nullable="name"),
    Case("user", _me, {"last_name": "Lovelace"}, non_nullable="username", nullable="first_name"),
]


async def _current(client: AsyncClient, url: str, headers: Headers) -> dict[str, Any]:
    response = await client.patch(url, json={}, headers=headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_patch_leaves_omitted_fields_unchanged(
    client: AsyncClient, auth_headers: Headers, case: Case
) -> None:
    url = await case.setup(client, auth_headers)
    before = await _current(client, url, auth_headers)

    response = await client.patch(url, json=case.other_update, headers=auth_headers)

    assert response.status_code == 200
    after = response.json()
    for key, value in case.other_update.items():
        assert after[key] == value
    unchanged = before.keys() - case.other_update.keys() - {"updated_at"}
    assert {k: after[k] for k in unchanged} == {k: before[k] for k in unchanged}


@pytest.mark.parametrize("case", [c for c in CASES if c.nullable], ids=lambda c: c.id)
async def test_patch_null_clears_nullable_field(
    client: AsyncClient, auth_headers: Headers, case: Case
) -> None:
    assert case.nullable is not None
    url = await case.setup(client, auth_headers)
    assert (await _current(client, url, auth_headers))[case.nullable] is not None

    response = await client.patch(url, json={case.nullable: None}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[case.nullable] is None
    assert (await _current(client, url, auth_headers))[case.nullable] is None


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_patch_null_on_non_nullable_field_returns_422(
    client: AsyncClient, auth_headers: Headers, case: Case
) -> None:
    url = await case.setup(client, auth_headers)
    before = await _current(client, url, auth_headers)

    response = await client.patch(url, json={case.non_nullable: None}, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", case.non_nullable]
    assert (await _current(client, url, auth_headers))[case.non_nullable] == before[case.non_nullable]

from typing import Any, cast

import pytest
from httpx import AsyncClient

TRIP_PAYLOAD = {"name": "Wonderland Trail", "total_distance_m": 149_700}


async def _create_trip(client: AsyncClient, headers: dict[str, str], **overrides: object) -> dict[str, Any]:
    payload = TRIP_PAYLOAD | overrides
    response = await client.post("/api/v1/trips", json=payload, headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def test_create_trip_seeds_checklist_and_food_plan(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)

    assert trip["name"] == "Wonderland Trail"
    assert trip["trip_type"] == "loop"
    assert len(trip["checklist_items"]) == 9
    assert all(item["checked"] is False for item in trip["checklist_items"])
    assert trip["food_plan"] is not None
    assert trip["food_plan"]["target_kcal_per_day"] == 2700
    assert trip["food_plan"]["target_food_g_per_day"] == 794
    assert trip["food_plan"]["food"] == []
    assert trip["gear_list"] == []
    assert trip["notes"] == []


async def test_list_trips_is_scoped_to_owner(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    await _create_trip(client, auth_headers, name="Mine")
    await _create_trip(client, other_auth_headers, name="Theirs")

    response = await client.get("/api/v1/trips", headers=auth_headers)

    assert response.status_code == 200
    names = {t["name"] for t in response.json()}
    assert names == {"Mine"}


async def test_get_trip_404_for_unknown_id(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/trips/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert response.status_code == 404


async def test_get_trip_403_for_other_users_trip(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.get(f"/api/v1/trips/{trip['id']}", headers=other_auth_headers)

    assert response.status_code == 403


async def test_update_trip(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}",
        json={"total_distance_m": 150_200.5, "name": "Wonderful Trail"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_distance_m"] == 150_200.5
    assert body["name"] == "Wonderful Trail"


async def test_delete_trip(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    delete_response = await client.delete(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert get_response.status_code == 404


async def test_notes_add_update_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    add_response = await client.post(
        f"/api/v1/trips/{trip['id']}/notes", json={"content": "Bring extra socks."}, headers=auth_headers
    )
    assert add_response.status_code == 201
    note = add_response.json()

    update_response = await client.patch(
        f"/api/v1/trips/{trip['id']}/notes/{note['id']}",
        json={"content": "Bring extra wool socks."},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "Bring extra wool socks."

    delete_response = await client.delete(
        f"/api/v1/trips/{trip['id']}/notes/{note['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204


async def test_checklist_item_update_by_key(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}/checklist/water_sources",
        json={"checked": True, "details": "Two reliable springs"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["item"] == "water_sources"
    assert body["checked"] is True
    assert body["details"] == "Two reliable springs"


async def test_food_plan_update_and_items(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    plan_response = await client.patch(
        f"/api/v1/trips/{trip['id']}/food-plan",
        json={"target_kcal_per_day": 3000, "target_food_g_per_day": 900},
        headers=auth_headers,
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["target_kcal_per_day"] == 3000

    add_response = await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": "Day 1", "name": "Oatmeal", "weight_g": 100, "kcal": 400},
        headers=auth_headers,
    )
    assert add_response.status_code == 201
    food = add_response.json()
    assert food["meal_type"] == "breakfast"

    update_response = await client.patch(
        f"/api/v1/trips/{trip['id']}/food-plan/items/{food['id']}",
        json={"kcal": 450},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["kcal"] == 450

    delete_response = await client.delete(
        f"/api/v1/trips/{trip['id']}/food-plan/items/{food['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    trip_after = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert trip_after.json()["food_plan"]["food"] == []


async def test_trip_dates_are_calendar_dates(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers, start_date="2026-08-26", end_date="2026-08-26")

    assert trip["start_date"] == "2026-08-26"
    assert trip["end_date"] == "2026-08-26"


async def test_create_trip_rejects_datetime_with_time(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/trips",
        json=TRIP_PAYLOAD | {"start_date": "2026-08-26T22:00:00-04:00"},
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_create_trip_rejects_end_date_before_start_date(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/trips",
        json=TRIP_PAYLOAD | {"start_date": "2026-08-26", "end_date": "2026-08-25"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "end_date"]


@pytest.mark.parametrize(
    ("update", "bad_field"),
    [
        ({"end_date": "2026-08-25"}, "end_date"),
        ({"start_date": "2026-08-30"}, "start_date"),
        ({"start_date": "2026-08-30", "end_date": "2026-08-29"}, "end_date"),
    ],
)
async def test_update_trip_rejects_dates_out_of_order_with_stored_values(
    client: AsyncClient, auth_headers: dict[str, str], update: dict[str, str], bad_field: str
) -> None:
    trip = await _create_trip(client, auth_headers, start_date="2026-08-26", end_date="2026-08-29")

    response = await client.patch(f"/api/v1/trips/{trip['id']}", json=update, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", bad_field]
    after = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)).json()
    assert (after["start_date"], after["end_date"]) == ("2026-08-26", "2026-08-29")


async def test_update_trip_can_move_both_dates_past_old_end_date(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers, start_date="2026-08-26", end_date="2026-08-29")

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}",
        json={"start_date": "2026-09-10", "end_date": "2026-09-12"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert (response.json()["start_date"], response.json()["end_date"]) == ("2026-09-10", "2026-09-12")


async def _trip_gear_url(client: AsyncClient, headers: dict[str, str], trip_id: str) -> str:
    item = await client.post("/api/v1/gear", json={"name": "Tent", "category": "shelter"}, headers=headers)
    response = await client.post(
        f"/api/v1/trips/{trip_id}/gear", json={"gear_item_id": item.json()["id"]}, headers=headers
    )
    return f"/api/v1/trips/{trip_id}/gear/{response.json()['id']}"


async def _food_item_url(client: AsyncClient, headers: dict[str, str], trip_id: str) -> str:
    response = await client.post(
        f"/api/v1/trips/{trip_id}/food-plan/items",
        json={"day": "Day 1", "name": "Oatmeal", "weight_g": 100, "kcal": 400},
        headers=headers,
    )
    return f"/api/v1/trips/{trip_id}/food-plan/items/{response.json()['id']}"


@pytest.mark.parametrize(
    ("method", "path", "body", "field"),
    [
        ("POST", "/api/v1/trips", TRIP_PAYLOAD | {"total_distance_m": -1}, "total_distance_m"),
        ("POST", "/api/v1/trips", TRIP_PAYLOAD | {"elevation_gain_m": -1}, "elevation_gain_m"),
        ("PATCH", "{trip}", {"total_distance_m": -0.5}, "total_distance_m"),
        ("POST", "/api/v1/gear", {"name": "Tent", "category": "shelter", "weight_g": -1}, "weight_g"),
        ("PATCH", "{trip_gear}", {"quantity": 0}, "quantity"),
        (
            "POST",
            "{trip}/food-plan/items",
            {"day": "Day 1", "name": "Tea", "weight_g": -1, "kcal": 0},
            "weight_g",
        ),
        (
            "POST",
            "{trip}/food-plan/items",
            {"day": "Day 1", "name": "Tea", "weight_g": 0, "kcal": -1},
            "kcal",
        ),
        ("PATCH", "{food}", {"kcal": -1}, "kcal"),
        ("PATCH", "{trip}/food-plan", {"target_kcal_per_day": -1}, "target_kcal_per_day"),
        ("PATCH", "{trip}/food-plan", {"target_food_g_per_day": -1}, "target_food_g_per_day"),
    ],
)
async def test_negative_numbers_are_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    body: dict[str, Any],
    field: str,
) -> None:
    trip = await _create_trip(client, auth_headers)
    trip_url = f"/api/v1/trips/{trip['id']}"
    urls = {"trip": trip_url}
    if "{trip_gear}" in path:
        urls["trip_gear"] = await _trip_gear_url(client, auth_headers, trip["id"])
    if "{food}" in path:
        urls["food"] = await _food_item_url(client, auth_headers, trip["id"])

    response = await client.request(method, path.format(**urls), json=body, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


async def test_zero_is_allowed_for_weights_and_calories(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers, total_distance_m=0, elevation_gain_m=0)

    gear = await client.post(
        "/api/v1/gear", json={"name": "Permit", "category": "docs", "weight_g": 0}, headers=auth_headers
    )
    food = await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": "Day 1", "name": "Tea", "weight_g": 0, "kcal": 0},
        headers=auth_headers,
    )

    assert (gear.status_code, food.status_code) == (201, 201)

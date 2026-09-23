from typing import Any, cast

from httpx import AsyncClient

TRIP_PAYLOAD = {"name": "Wonderland Trail", "total_distance": 93}


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
    assert trip["measurements"] == "imperial"
    assert trip["trip_type"] == "loop"
    assert len(trip["checklist_items"]) == 9
    assert all(item["checked"] is False for item in trip["checklist_items"])
    assert trip["food_plan"] is not None
    assert trip["food_plan"]["target_calories"] == 0
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
        json={"total_distance": 100, "name": "Wonderful Trail"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_distance"] == 100
    assert body["name"] == "Wonderful Trail"


async def test_delete_trip(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    delete_response = await client.delete(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert get_response.status_code == 404


async def test_gear_add_update_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)

    add_response = await client.post(
        f"/api/v1/trips/{trip['id']}/gear",
        json={"gear_name": "Tent", "category": "SHELTER", "weight": 1.2, "quantity": 1},
        headers=auth_headers,
    )
    assert add_response.status_code == 201
    gear = add_response.json()
    assert gear["gear_name"] == "Tent"
    assert gear["category"] == "shelter"

    update_response = await client.patch(
        f"/api/v1/trips/{trip['id']}/gear/{gear['id']}",
        json={"gear_name": "Tarp", "quantity": 2},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["gear_name"] == "Tarp"
    assert update_response.json()["quantity"] == 2

    delete_response = await client.delete(
        f"/api/v1/trips/{trip['id']}/gear/{gear['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    trip_after = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert trip_after.json()["gear_list"] == []


async def test_gear_not_found_for_other_users_trip(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.post(
        f"/api/v1/trips/{trip['id']}/gear",
        json={"gear_name": "Tent", "category": "shelter"},
        headers=other_auth_headers,
    )

    assert response.status_code == 403


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
        json={"target_calories": 12000, "target_food_weight": 6.5},
        headers=auth_headers,
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["target_calories"] == 12000

    add_response = await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": "Day 1", "name": "Oatmeal", "weight": 0.1, "calories": 400},
        headers=auth_headers,
    )
    assert add_response.status_code == 201
    food = add_response.json()
    assert food["meal_type"] == "breakfast"

    update_response = await client.patch(
        f"/api/v1/trips/{trip['id']}/food-plan/items/{food['id']}",
        json={"calories": 450},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["calories"] == 450

    delete_response = await client.delete(
        f"/api/v1/trips/{trip['id']}/food-plan/items/{food['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    trip_after = await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)
    assert trip_after.json()["food_plan"]["food"] == []

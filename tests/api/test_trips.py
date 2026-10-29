import uuid
from typing import Any, cast

import pytest
from httpx import AsyncClient

from app.schemas.base import INT32_MAX

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
    statuses = {item["item"]: item["status"] for item in trip["checklist_items"]}
    assert statuses.pop("shuttle_scheduled") == "not_applicable"  # loop trips need no shuttle
    assert set(statuses.values()) == {"todo"}
    assert trip["checklist_ready"] is False
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


async def test_get_trip_404_for_other_users_trip(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)

    response = await client.get(f"/api/v1/trips/{trip['id']}", headers=other_auth_headers)
    missing = await client.get(f"/api/v1/trips/{uuid.uuid4()}", headers=other_auth_headers)

    assert response.status_code == 404
    assert response.json() == missing.json()


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
        json={"status": "done", "details": "Two reliable springs"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["item"] == "water_sources"
    assert body["status"] == "done"
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
        json={"day": 1, "name": "Oatmeal", "weight_g": 100, "kcal": 400},
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
        json={"day": 1, "name": "Oatmeal", "weight_g": 100, "kcal": 400},
        headers=headers,
    )
    return f"/api/v1/trips/{trip_id}/food-plan/items/{response.json()['id']}"


@pytest.mark.parametrize(
    ("method", "path", "body", "field"),
    [
        ("POST", "/api/v1/trips", TRIP_PAYLOAD | {"total_distance_m": -1}, "total_distance_m"),
        ("POST", "/api/v1/trips", TRIP_PAYLOAD | {"elevation_gain_m": -1}, "elevation_gain_m"),
        ("POST", "/api/v1/trips", TRIP_PAYLOAD | {"water_carry_l": -1}, "water_carry_l"),
        ("PATCH", "{trip}", {"water_carry_l": None}, "water_carry_l"),
        ("POST", "{trip}/food-plan/items", {"day": 0, "name": "Tea", "weight_g": 0, "kcal": 0}, "day"),
        (
            "POST",
            "{trip}/food-plan/items",
            {"day": 1, "name": "Tea", "weight_g": 0, "kcal": 0, "servings": 0},
            "servings",
        ),
        ("PATCH", "{food}", {"servings": -1}, "servings"),
        ("PATCH", "{trip}", {"total_distance_m": -0.5}, "total_distance_m"),
        ("POST", "/api/v1/gear", {"name": "Tent", "category": "shelter", "weight_g": -1}, "weight_g"),
        ("PATCH", "{trip_gear}", {"quantity": 0}, "quantity"),
        (
            "POST",
            "{trip}/food-plan/items",
            {"day": 1, "name": "Tea", "weight_g": -1, "kcal": 0},
            "weight_g",
        ),
        (
            "POST",
            "{trip}/food-plan/items",
            {"day": 1, "name": "Tea", "weight_g": 0, "kcal": -1},
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
    url = await _numeric_field_url(client, auth_headers, path)

    response = await client.request(method, url, json=body, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


INT_FIELDS = [
    pytest.param(
        "POST", "{trip}/food-plan/items", {"name": "Tea", "weight_g": 0, "kcal": 0}, "day", id="create-day"
    ),
    pytest.param(
        "POST", "{trip}/food-plan/items", {"day": 1, "name": "Tea", "weight_g": 0}, "kcal", id="create-kcal"
    ),
    pytest.param("PATCH", "{food}", {}, "day", id="update-day"),
    pytest.param("PATCH", "{food}", {}, "kcal", id="update-kcal"),
    pytest.param("PATCH", "{trip}/food-plan", {}, "target_kcal_per_day", id="target-kcal"),
    pytest.param("POST", "{trip}/gear", {}, "quantity", id="create-quantity"),
    pytest.param("PATCH", "{trip_gear}", {}, "quantity", id="update-quantity"),
]


@pytest.mark.parametrize(("method", "path", "body", "field"), INT_FIELDS)
async def test_int_fields_reject_values_beyond_int32(
    client: AsyncClient,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    body: dict[str, Any],
    field: str,
) -> None:
    url = await _numeric_field_url(client, auth_headers, path)
    body = body | await _gear_item_ref(client, auth_headers, path) | {field: INT32_MAX + 1}

    response = await client.request(method, url, json=body, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize(("method", "path", "body", "field"), INT_FIELDS)
async def test_int_fields_accept_int32_max(
    client: AsyncClient,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    body: dict[str, Any],
    field: str,
) -> None:
    url = await _numeric_field_url(client, auth_headers, path)
    body = body | await _gear_item_ref(client, auth_headers, path) | {field: INT32_MAX}

    response = await client.request(method, url, json=body, headers=auth_headers)

    assert response.status_code in (200, 201)
    assert response.json()[field] == INT32_MAX


async def _numeric_field_url(client: AsyncClient, headers: dict[str, str], path: str) -> str:
    """Create a trip (plus the trip gear or food item ``path`` refers to) and fill in ``path``."""
    trip = await _create_trip(client, headers)
    urls = {"trip": f"/api/v1/trips/{trip['id']}"}
    if "{trip_gear}" in path:
        urls["trip_gear"] = await _trip_gear_url(client, headers, trip["id"])
    if "{food}" in path:
        urls["food"] = await _food_item_url(client, headers, trip["id"])
    return path.format(**urls)


async def _gear_item_ref(client: AsyncClient, headers: dict[str, str], path: str) -> dict[str, Any]:
    """The closet item a POST to a trip's gear list needs; nothing for any other path."""
    if path != "{trip}/gear":
        return {}
    item = await client.post(
        "/api/v1/gear", json={"name": "Stove", "category": "cooking_water"}, headers=headers
    )
    return {"gear_item_id": item.json()["id"]}


async def test_zero_is_allowed_for_weights_and_calories(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers, total_distance_m=0, elevation_gain_m=0)

    gear = await client.post(
        "/api/v1/gear", json={"name": "Permit", "category": "misc", "weight_g": 0}, headers=auth_headers
    )
    food = await client.post(
        f"/api/v1/trips/{trip['id']}/food-plan/items",
        json={"day": 1, "name": "Tea", "weight_g": 0, "kcal": 0},
        headers=auth_headers,
    )

    assert (gear.status_code, food.status_code) == (201, 201)


async def test_trip_area_and_water_carry(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers, area="Pisgah")
    assert (trip["area"], trip["water_carry_l"]) == ("Pisgah", 0)

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}", json={"water_carry_l": 2.5, "area": None}, headers=auth_headers
    )

    assert response.status_code == 200
    assert (response.json()["area"], response.json()["water_carry_l"]) == (None, 2.5)


async def test_food_item_day_and_servings(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    trip = await _create_trip(client, auth_headers)
    url = f"/api/v1/trips/{trip['id']}/food-plan/items"

    default = await client.post(
        url, json={"day": 1, "name": "Oatmeal", "weight_g": 100, "kcal": 400}, headers=auth_headers
    )
    half = await client.post(
        url,
        json={"day": 2, "name": "Oatmeal", "weight_g": 100, "kcal": 400, "servings": 1.5},
        headers=auth_headers,
    )
    labelled_day = await client.post(
        url, json={"day": "Day 1", "name": "Oatmeal", "weight_g": 100, "kcal": 400}, headers=auth_headers
    )

    assert (default.status_code, default.json()["day"], default.json()["servings"]) == (201, 1, 1)
    assert (half.status_code, half.json()["servings"]) == (201, 1.5)
    assert labelled_day.status_code == 422


def _shuttle_status(trip: dict[str, Any]) -> str:
    return str(next(i["status"] for i in trip["checklist_items"] if i["item"] == "shuttle_scheduled"))


async def test_checklist_ready_when_nothing_left_to_do(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    url = f"/api/v1/trips/{trip['id']}"
    todo = [i["item"] for i in trip["checklist_items"] if i["status"] == "todo"]

    for key in todo[:-1]:
        await client.patch(f"{url}/checklist/{key}", json={"status": "done"}, headers=auth_headers)
    assert (await client.get(url, headers=auth_headers)).json()["checklist_ready"] is False

    await client.patch(
        f"{url}/checklist/{todo[-1]}", json={"status": "not_applicable"}, headers=auth_headers
    )
    assert (await client.get(url, headers=auth_headers)).json()["checklist_ready"] is True


async def test_changing_trip_type_keeps_shuttle_item_in_step(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers, trip_type="loop")
    url = f"/api/v1/trips/{trip['id']}"

    to_point = await client.patch(url, json={"trip_type": "point-to-point"}, headers=auth_headers)
    back_to_loop = await client.patch(url, json={"trip_type": "out-and-back"}, headers=auth_headers)

    assert _shuttle_status(to_point.json()) == "todo"
    assert _shuttle_status(back_to_loop.json()) == "not_applicable"


async def test_changing_trip_type_never_undoes_a_done_shuttle(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers, trip_type="point-to-point")
    url = f"/api/v1/trips/{trip['id']}"
    await client.patch(f"{url}/checklist/shuttle_scheduled", json={"status": "done"}, headers=auth_headers)

    response = await client.patch(url, json={"trip_type": "loop"}, headers=auth_headers)

    assert _shuttle_status(response.json()) == "done"


async def test_checklist_rejects_unknown_status_and_old_permit_key(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    trip = await _create_trip(client, auth_headers)
    url = f"/api/v1/trips/{trip['id']}/checklist"

    bad_status = await client.patch(f"{url}/permit", json={"status": "n/a"}, headers=auth_headers)
    old_key = await client.patch(f"{url}/permit_required", json={"status": "done"}, headers=auth_headers)
    permit = await client.patch(f"{url}/permit", json={"status": "not_applicable"}, headers=auth_headers)

    assert (bad_status.status_code, old_key.status_code) == (422, 422)
    assert (permit.status_code, permit.json()["status"]) == (200, "not_applicable")


@pytest.mark.parametrize("link", ["https://caltopo.com/m/ABC", "http://example.com/map?x=1"])
async def test_map_link_accepts_http_urls(
    client: AsyncClient, auth_headers: dict[str, str], link: str
) -> None:
    trip = await _create_trip(client, auth_headers, map_link=f"  {link}  ")

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}", json={"map_link": link}, headers=auth_headers
    )

    assert trip["map_link"] == link
    assert (response.status_code, response.json()["map_link"]) == (200, link)


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        " javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.test",
        "ftp://example.com/map",
        "https://",
        "caltopo.com/m/ABC",
        "http://[::1",
    ],
)
async def test_map_link_rejects_non_http_urls(
    client: AsyncClient, auth_headers: dict[str, str], link: str
) -> None:
    trip = await _create_trip(client, auth_headers, map_link="https://caltopo.com/m/ABC")

    created = await client.post(
        "/api/v1/trips", json=TRIP_PAYLOAD | {"map_link": link}, headers=auth_headers
    )
    updated = await client.patch(
        f"/api/v1/trips/{trip['id']}", json={"map_link": link}, headers=auth_headers
    )

    for response in (created, updated):
        assert response.status_code == 422
        error = response.json()["detail"][0]
        assert error["loc"] == ["body", "map_link"]
        assert "Map link must start with http:// or https://" in error["msg"]
    after = (await client.get(f"/api/v1/trips/{trip['id']}", headers=auth_headers)).json()
    assert after["map_link"] == "https://caltopo.com/m/ABC"


@pytest.mark.parametrize("cleared", [None, "", "   "])
async def test_map_link_can_be_cleared(
    client: AsyncClient, auth_headers: dict[str, str], cleared: str | None
) -> None:
    trip = await _create_trip(client, auth_headers, map_link="https://caltopo.com/m/ABC")

    response = await client.patch(
        f"/api/v1/trips/{trip['id']}", json={"map_link": cleared}, headers=auth_headers
    )

    assert (response.status_code, response.json()["map_link"]) == (200, None)


# (create path, valid create body, field that must not be blank). Each resource's PATCH url is
# its create path plus the new id.
REQUIRED_TEXT_FIELDS = [
    pytest.param("/api/v1/trips", TRIP_PAYLOAD, "name", id="trip"),
    pytest.param("/api/v1/gear", {"name": "Tent"}, "name", id="gear-item"),
    pytest.param("{trip}/notes", {"content": "Bring extra socks."}, "content", id="note"),
    pytest.param(
        "{trip}/food-plan/items",
        {"day": 1, "name": "Oatmeal", "weight_g": 100, "kcal": 400},
        "name",
        id="food",
    ),
]


async def _create_path(client: AsyncClient, headers: dict[str, str], path: str) -> str:
    if "{trip}" not in path:
        return path
    trip = await _create_trip(client, headers)
    return path.format(trip=f"/api/v1/trips/{trip['id']}")


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize(("path", "body", "field"), REQUIRED_TEXT_FIELDS)
async def test_required_text_fields_reject_blank_values(
    client: AsyncClient,
    auth_headers: dict[str, str],
    path: str,
    body: dict[str, Any],
    field: str,
    blank: str,
) -> None:
    path = await _create_path(client, auth_headers, path)
    created = await client.post(path, json=body, headers=auth_headers)
    url = f"{path}/{created.json()['id']}"

    rejected_create = await client.post(path, json=body | {field: blank}, headers=auth_headers)
    rejected_update = await client.patch(url, json={field: blank}, headers=auth_headers)

    for response in (rejected_create, rejected_update):
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", field]
    after = await client.patch(url, json={}, headers=auth_headers)
    assert after.json()[field] == body[field]


@pytest.mark.parametrize(("path", "body", "field"), REQUIRED_TEXT_FIELDS)
async def test_required_text_fields_are_stored_stripped(
    client: AsyncClient, auth_headers: dict[str, str], path: str, body: dict[str, Any], field: str
) -> None:
    path = await _create_path(client, auth_headers, path)

    created = await client.post(path, json=body | {field: "  First  "}, headers=auth_headers)
    updated = await client.patch(
        f"{path}/{created.json()['id']}", json={field: "\tSecond\n"}, headers=auth_headers
    )

    assert (created.status_code, created.json()[field]) == (201, "First")
    assert (updated.status_code, updated.json()[field]) == (200, "Second")

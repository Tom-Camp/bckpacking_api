from typing import Any, cast

from httpx import AsyncClient

from tests.api.test_trips import _create_trip

Headers = dict[str, str]


async def _create_item(client: AsyncClient, headers: Headers, **overrides: object) -> dict[str, Any]:
    payload = {"name": "Tent", "category": "shelter", "weight_g": 1200} | overrides
    response = await client.post("/api/v1/gear", json=payload, headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def _pack(client: AsyncClient, headers: Headers, trip_id: str, item_id: str, **extra: object) -> Any:
    return await client.post(
        f"/api/v1/trips/{trip_id}/gear", json={"gear_item_id": item_id} | extra, headers=headers
    )


async def _trip_gear(client: AsyncClient, headers: Headers, trip_id: str) -> list[dict[str, Any]]:
    trip = (await client.get(f"/api/v1/trips/{trip_id}", headers=headers)).json()
    return cast(list[dict[str, Any]], trip["gear_list"])


# --- closet -------------------------------------------------------------------------------------


async def test_create_and_read_gear_item(client: AsyncClient, auth_headers: Headers) -> None:
    item = await _create_item(client, auth_headers, category="SHELTER")

    assert item["category"] == "shelter"
    assert item["kind"] == "base"
    assert item["archived_at"] is None
    fetched = await client.get(f"/api/v1/gear/{item['id']}", headers=auth_headers)
    assert fetched.json() == item


async def test_list_gear_items_is_scoped_to_owner(
    client: AsyncClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    await _create_item(client, auth_headers, name="Mine")
    await _create_item(client, other_auth_headers, name="Theirs")

    response = await client.get("/api/v1/gear", headers=auth_headers)

    assert [i["name"] for i in response.json()] == ["Mine"]


async def test_other_users_gear_item_is_not_found(
    client: AsyncClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    item = await _create_item(client, auth_headers)
    url = f"/api/v1/gear/{item['id']}"

    responses = [
        await client.get(url, headers=other_auth_headers),
        await client.patch(url, json={"name": "Stolen"}, headers=other_auth_headers),
        await client.delete(url, headers=other_auth_headers),
        await client.post(f"{url}/restore", headers=other_auth_headers),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert (await client.get(url, headers=auth_headers)).json()["archived_at"] is None


async def test_archive_hides_item_from_closet_and_restore_brings_it_back(
    client: AsyncClient, auth_headers: Headers
) -> None:
    item = await _create_item(client, auth_headers)
    url = f"/api/v1/gear/{item['id']}"

    assert (await client.delete(url, headers=auth_headers)).status_code == 204
    assert (await client.delete(url, headers=auth_headers)).status_code == 204  # repeat is harmless
    assert (await client.get("/api/v1/gear", headers=auth_headers)).json() == []
    archived = (await client.get("/api/v1/gear?include_archived=true", headers=auth_headers)).json()
    assert [i["id"] for i in archived] == [item["id"]]
    assert archived[0]["archived_at"] is not None

    restored = await client.post(f"{url}/restore", headers=auth_headers)

    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [i["id"] for i in (await client.get("/api/v1/gear", headers=auth_headers)).json()] == [item["id"]]


# --- trip gear ----------------------------------------------------------------------------------


async def test_pack_closet_item_for_trip(client: AsyncClient, auth_headers: Headers) -> None:
    trip = await _create_trip(client, auth_headers)
    item = await _create_item(client, auth_headers)

    response = await _pack(client, auth_headers, trip["id"], item["id"])

    assert response.status_code == 201
    trip_gear = response.json()
    assert trip_gear["gear_item"] == item
    assert (trip_gear["quantity"], trip_gear["packed"]) == (1, False)
    assert [tg["id"] for tg in await _trip_gear(client, auth_headers, trip["id"])] == [trip_gear["id"]]


async def test_editing_closet_item_updates_every_trip(client: AsyncClient, auth_headers: Headers) -> None:
    item = await _create_item(client, auth_headers, weight_g=1200)
    trips = [await _create_trip(client, auth_headers, name=name) for name in ("One", "Two")]
    for trip in trips:
        await _pack(client, auth_headers, trip["id"], item["id"])

    await client.patch(f"/api/v1/gear/{item['id']}", json={"weight_g": 1180}, headers=auth_headers)

    for trip in trips:
        [trip_gear] = await _trip_gear(client, auth_headers, trip["id"])
        assert trip_gear["gear_item"]["weight_g"] == 1180


async def test_packing_same_item_twice_conflicts(client: AsyncClient, auth_headers: Headers) -> None:
    trip = await _create_trip(client, auth_headers)
    item = await _create_item(client, auth_headers)
    await _pack(client, auth_headers, trip["id"], item["id"])

    response = await _pack(client, auth_headers, trip["id"], item["id"])

    assert response.status_code == 409
    assert len(await _trip_gear(client, auth_headers, trip["id"])) == 1


async def test_archived_item_cannot_be_packed_but_stays_on_existing_trips(
    client: AsyncClient, auth_headers: Headers
) -> None:
    item = await _create_item(client, auth_headers)
    old_trip = await _create_trip(client, auth_headers, name="Old")
    await _pack(client, auth_headers, old_trip["id"], item["id"])
    await client.delete(f"/api/v1/gear/{item['id']}", headers=auth_headers)
    new_trip = await _create_trip(client, auth_headers, name="New")

    response = await _pack(client, auth_headers, new_trip["id"], item["id"])

    assert response.status_code == 409
    [old_gear] = await _trip_gear(client, auth_headers, old_trip["id"])
    assert old_gear["gear_item"]["archived_at"] is not None


async def test_cannot_pack_another_users_or_unknown_item(
    client: AsyncClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    trip = await _create_trip(client, auth_headers)
    their_item = await _create_item(client, other_auth_headers)

    responses = [
        await _pack(client, auth_headers, trip["id"], their_item["id"]),
        await _pack(client, auth_headers, trip["id"], "00000000-0000-0000-0000-000000000000"),
    ]

    assert [r.status_code for r in responses] == [404, 404]
    assert await _trip_gear(client, auth_headers, trip["id"]) == []


async def test_update_and_remove_trip_gear(client: AsyncClient, auth_headers: Headers) -> None:
    trip = await _create_trip(client, auth_headers)
    item = await _create_item(client, auth_headers)
    trip_gear = (await _pack(client, auth_headers, trip["id"], item["id"])).json()
    url = f"/api/v1/trips/{trip['id']}/gear/{trip_gear['id']}"

    updated = await client.patch(url, json={"quantity": 2, "packed": True}, headers=auth_headers)

    assert updated.status_code == 200
    assert (updated.json()["quantity"], updated.json()["packed"]) == (2, True)

    assert (await client.delete(url, headers=auth_headers)).status_code == 204
    assert await _trip_gear(client, auth_headers, trip["id"]) == []
    assert (await client.get(f"/api/v1/gear/{item['id']}", headers=auth_headers)).status_code == 200


async def test_trip_gear_from_another_trip_is_not_found(client: AsyncClient, auth_headers: Headers) -> None:
    trip = await _create_trip(client, auth_headers, name="One")
    other_trip = await _create_trip(client, auth_headers, name="Two")
    item = await _create_item(client, auth_headers)
    trip_gear = (await _pack(client, auth_headers, trip["id"], item["id"])).json()

    response = await client.patch(
        f"/api/v1/trips/{other_trip['id']}/gear/{trip_gear['id']}",
        json={"packed": True},
        headers=auth_headers,
    )

    assert response.status_code == 404


# --- copy from another trip ---------------------------------------------------------------------


async def test_copy_gear_from_trip(client: AsyncClient, auth_headers: Headers) -> None:
    tent = await _create_item(client, auth_headers, name="Tent")
    stove = await _create_item(client, auth_headers, name="Stove", category="cook")
    old_quilt = await _create_item(client, auth_headers, name="Old quilt", category="sleep")
    source = await _create_trip(client, auth_headers, name="Source")
    await _pack(client, auth_headers, source["id"], tent["id"], packed=True)
    await _pack(client, auth_headers, source["id"], stove["id"], quantity=2)
    await _pack(client, auth_headers, source["id"], old_quilt["id"])
    await client.delete(f"/api/v1/gear/{old_quilt['id']}", headers=auth_headers)
    target = await _create_trip(client, auth_headers, name="Target")
    await _pack(client, auth_headers, target["id"], tent["id"], quantity=3)
    url = f"/api/v1/trips/{target['id']}/gear/copy-from/{source['id']}"

    response = await client.post(url, headers=auth_headers)

    assert response.status_code == 200
    copied = {tg["gear_item"]["name"]: (tg["quantity"], tg["packed"]) for tg in response.json()}
    # Tent was already on the target (kept as-is), Stove copied unpacked, archived Old quilt skipped.
    assert copied == {"Tent": (3, False), "Stove": (2, False)}
    assert len(await _trip_gear(client, auth_headers, target["id"])) == 2

    repeat = await client.post(url, headers=auth_headers)
    assert len(repeat.json()) == 2


async def test_copy_gear_from_another_users_or_unknown_trip_is_not_found(
    client: AsyncClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    target = await _create_trip(client, auth_headers)
    theirs = await _create_trip(client, other_auth_headers)

    responses = [
        await client.post(f"/api/v1/trips/{target['id']}/gear/copy-from/{source_id}", headers=auth_headers)
        for source_id in (theirs["id"], "00000000-0000-0000-0000-000000000000")
    ]

    assert [r.status_code for r in responses] == [404, 404]

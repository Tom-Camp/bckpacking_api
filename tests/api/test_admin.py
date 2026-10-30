import re
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from app.auth.tokens import create_access_token
from app.main import app
from app.models.gear import GearItem
from app.models.trip import Trip, TripGear
from app.models.user import User, UserRole, UserStatus
from tests.api.conftest import _make_active_user


@pytest_asyncio.fixture
async def admin(session: AsyncSession) -> User:
    admin_user = await _make_active_user(session, "admin@example.com", "admin")
    admin_user.role = UserRole.ADMIN
    session.add(admin_user)
    await session.commit()
    return admin_user


@pytest.fixture
def admin_headers(admin: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin)}"}


def _admin_routes() -> list[tuple[str, str]]:
    # From the OpenAPI schema, so a new admin route is covered without editing this file.
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/admin")
        for method in operations
    )


def _url(path: str, user_id: uuid.UUID) -> str:
    return re.sub(r"\{[^}]+\}", str(user_id), path)


def _body(path: str) -> dict[str, str] | None:
    return {"role": "user"} if path.endswith("/role") else None


@pytest.mark.parametrize(("method", "path"), _admin_routes())
async def test_non_admin_gets_403_on_every_admin_route(
    client: AsyncClient, user: User, other_user: User, auth_headers: dict[str, str], method: str, path: str
) -> None:
    response = await client.request(
        method, _url(path, other_user.id), json=_body(path), headers=auth_headers
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


@pytest.mark.parametrize(("method", "path"), [r for r in _admin_routes() if "{user_id}" in r[1]])
async def test_unknown_user_id_gets_404(
    client: AsyncClient, admin_headers: dict[str, str], method: str, path: str
) -> None:
    response = await client.request(
        method, _url(path, uuid.uuid4()), json=_body(path), headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


async def test_list_users_filters_by_status(
    client: AsyncClient, session: AsyncSession, admin: User, user: User, admin_headers: dict[str, str]
) -> None:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()

    everyone = await client.get("/api/v1/admin/users", headers=admin_headers)
    blocked = await client.get("/api/v1/admin/users", params={"status": "blocked"}, headers=admin_headers)
    active = await client.get("/api/v1/admin/users", params={"status": "active"}, headers=admin_headers)

    assert {u["username"] for u in everyone.json()} == {"admin", "hiker"}
    assert [u["username"] for u in blocked.json()] == ["hiker"]
    assert [u["username"] for u in active.json()] == ["admin"]


async def test_get_user(client: AsyncClient, user: User, admin_headers: dict[str, str]) -> None:
    response = await client.get(f"/api/v1/admin/users/{user.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["email"] == user.email


async def test_suspend_then_approve_changes_status(
    client: AsyncClient, user: User, admin_headers: dict[str, str]
) -> None:
    suspended = await client.patch(f"/api/v1/admin/users/{user.id}/suspend", headers=admin_headers)
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "blocked"

    approved = await client.patch(f"/api/v1/admin/users/{user.id}/approve", headers=admin_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"


async def test_set_role_changes_role(client: AsyncClient, user: User, admin_headers: dict[str, str]) -> None:
    response = await client.patch(
        f"/api/v1/admin/users/{user.id}/role", json={"role": "admin"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_set_role_rejects_unknown_role(
    client: AsyncClient, user: User, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/admin/users/{user.id}/role", json={"role": "superuser"}, headers=admin_headers
    )

    assert response.status_code == 422


async def test_delete_user_removes_their_trips_and_closet(
    client: AsyncClient,
    session: AsyncSession,
    user: User,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    item = await client.post("/api/v1/gear", json={"name": "Tent", "weight_g": 1200}, headers=auth_headers)
    trip = await client.post("/api/v1/trips", json={"name": "Wonderland Trail"}, headers=auth_headers)
    added = await client.post(
        f"/api/v1/trips/{trip.json()['id']}/gear",
        json={"gear_item_id": item.json()["id"]},
        headers=auth_headers,
    )
    assert added.status_code == 201
    user_id = user.id

    response = await client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)

    assert response.status_code == 204
    session.expunge_all()
    assert await session.get(User, user_id) is None
    for model in (Trip, GearItem):
        count = await session.scalar(select(func.count()).where(col(model.user_id) == user_id))
        assert count == 0, model.__name__
    assert await session.scalar(select(func.count()).select_from(TripGear)) == 0


@pytest.mark.parametrize(
    ("method", "suffix", "body", "detail"),
    [
        ("DELETE", "", None, "Cannot delete your own account"),
        ("PATCH", "/suspend", None, "Cannot suspend your own account"),
        ("PATCH", "/role", {"role": "user"}, "Cannot change your own role"),
    ],
)
async def test_admin_cannot_lock_themselves_out(
    client: AsyncClient,
    session: AsyncSession,
    admin: User,
    admin_headers: dict[str, str],
    method: str,
    suffix: str,
    body: dict[str, str] | None,
    detail: str,
) -> None:
    response = await client.request(
        method, f"/api/v1/admin/users/{admin.id}{suffix}", json=body, headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail
    await session.refresh(admin)
    assert admin.role == UserRole.ADMIN
    assert admin.status == UserStatus.ACTIVE

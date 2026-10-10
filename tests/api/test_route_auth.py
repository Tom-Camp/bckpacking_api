import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import app

# The only routes an anonymous caller may reach. shared.py is read-only and scoped to its share token.
_PUBLIC_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
}
_PUBLIC_PREFIX = "/api/v1/shared/"


def _authenticated_routes() -> list[tuple[str, str]]:
    # From the OpenAPI schema: app.routes nests included routers rather than listing their routes.
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if not path.startswith(_PUBLIC_PREFIX)
        for method in operations
        if (method.upper(), path) not in _PUBLIC_ROUTES
    )


def test_public_routes_exist() -> None:
    # Keeps the allowlist honest: a renamed public route must not linger here.
    paths = app.openapi()["paths"]
    for method, path in _PUBLIC_ROUTES:
        assert method.lower() in paths[path]


@pytest.mark.parametrize(("method", "path"), _authenticated_routes())
async def test_route_rejects_anonymous_request(client: AsyncClient, method: str, path: str) -> None:
    # The auth dependency runs before path and body validation, so a junk path param or body still gets 401.
    url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
    body: dict[str, object] | None = None if method in ("GET", "DELETE") else {}

    response = await client.request(method, url, json=body)

    assert response.status_code == 401, response.text

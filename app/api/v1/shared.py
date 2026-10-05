"""Public, unauthenticated read-only views reached through share links.

Kept apart from the authenticated routers so the public surface is easy to audit: GET only, no auth.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.trip import SharedTripRead
from app.services import trip as trip_service

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/trip", response_model=SharedTripRead)
async def get_shared_trip(
    response: Response,
    # The token is a credential, so it travels in a header rather than the URL, which proxies log.
    # Optional so a missing header gets the same 404 as a bad token instead of a revealing 422.
    share_token: str | None = Header(default=None, alias="X-Share-Token"),
    session: AsyncSession = Depends(get_session),
) -> SharedTripRead:
    trip = await trip_service.get_shared_trip(session, share_token) if share_token else None
    if not trip:
        # Same response for missing, empty, unknown, revoked, and blocked-owner tokens.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    # Keep the response out of caches and the viewer's outbound Referer headers.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return SharedTripRead.from_trip(trip)

"""Public, unauthenticated read-only views reached through share links.

Kept apart from the authenticated routers so the public surface is easy to audit: GET only, no auth.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.trip import SharedTripRead
from app.services import trip as trip_service

router = APIRouter(prefix="/shared", tags=["shared"])


@router.get("/trips/{share_token}", response_model=SharedTripRead)
async def get_shared_trip(
    share_token: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> SharedTripRead:
    trip = await trip_service.get_shared_trip(session, share_token)
    if not trip:
        # Same response for unknown, revoked, and blocked-owner tokens.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    # The token is the credential: keep it out of caches and outbound Referer headers.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return SharedTripRead.model_validate(trip)

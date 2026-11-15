from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import clear_refresh_cookie, set_refresh_cookie
from app.auth.tokens import create_access_token
from app.db import get_session
from app.schemas.user import TokenResponse
from app.services import refresh_token as refresh_token_service

# Not under /auth: nginx rate-limits /api/v1/auth/ per IP, and every tab refreshes on start.
# Authenticated by the refresh_token cookie (see auth/cookies.py), never a bearer token.
router = APIRouter(prefix="/session", tags=["session"])

INVALID_SESSION = "Invalid or expired session"


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": INVALID_SESSION},
        status.HTTP_403_FORBIDDEN: {"description": "Account suspended"},
    },
)
async def refresh_session(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse | JSONResponse:
    rotated = await refresh_token_service.rotate(session, refresh_token) if refresh_token else None
    if rotated is None:
        invalid = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": INVALID_SESSION})
        clear_refresh_cookie(invalid)
        return invalid
    user, new_raw = rotated
    set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=create_access_token(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_session),
) -> None:
    if refresh_token:
        await refresh_token_service.revoke(session, refresh_token)
    clear_refresh_cookie(response)

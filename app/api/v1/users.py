from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import set_refresh_cookie
from app.auth.dependencies import get_current_user, require_active_user
from app.auth.tokens import create_access_token
from app.db import get_session
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, TokenResponse, UserRead, UserUpdate
from app.services import refresh_token as refresh_token_service
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.update_user(session, user, data)
    return UserRead.model_validate(user)


@router.post("/me/password", response_model=TokenResponse)
async def change_my_password(
    data: ChangePasswordRequest,
    response: Response,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # The change revokes every earlier access and refresh token, this request's included, so hand back
    # fresh ones for this device
    await user_service.change_password(session, user, data)
    set_refresh_cookie(response, await refresh_token_service.issue(session, user))
    return TokenResponse(access_token=create_access_token(user))

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_active_user
from app.auth.tokens import create_access_token
from app.db import get_session
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, TokenResponse, UserRead, UserUpdate
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
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # The change revokes every earlier token, this request's included, so hand back a fresh one
    await user_service.change_password(session, user, data)
    return TokenResponse(access_token=create_access_token(user))

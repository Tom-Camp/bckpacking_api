import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_active_user
from app.db import get_session
from app.models.user import User
from app.schemas.user import UserPublic, UserRead, UserUpdate
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


@router.get("", response_model=list[UserPublic])
async def list_users(
    session: AsyncSession = Depends(get_session),
) -> list[UserPublic]:
    users = await user_service.list_users(session)
    return [UserPublic.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(user)

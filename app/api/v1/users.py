import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_active_user, require_admin
from app.db import get_session
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate
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


@router.get("", response_model=list[UserRead])
async def list_users(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[UserRead]:
    users = await user_service.list_users(session)
    return [UserRead.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if admin.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await user_service.delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

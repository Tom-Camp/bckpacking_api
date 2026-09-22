import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.dependencies import require_admin
from app.db import get_session
from app.models.user import User, UserStatus
from app.schemas.user import SetRoleRequest, UserRead
from app.services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserRead])
async def list_users(
    filter_status: UserStatus | None = Query(default=None, alias="status"),
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[UserRead]:
    query = select(User)
    if filter_status is not None:
        query = query.where(User.status == filter_status)
    result = await session.execute(query)
    return [UserRead.model_validate(u) for u in result.scalars().all()]


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}/approve", response_model=UserRead)
async def approve_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = await user_service.approve_user(session, user)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}/suspend", response_model=UserRead)
async def suspend_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = await user_service.suspend_user(session, user)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}/role", response_model=UserRead)
async def set_user_role(
    user_id: uuid.UUID,
    data: SetRoleRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = await user_service.set_role(session, user, data.role)
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
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

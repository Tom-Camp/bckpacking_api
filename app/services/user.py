import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.passwords import hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import UserCreate, UserLogin
from app.utils.config import settings

logger = structlog.get_logger()


def _maybe_bootstrap_admin(user: User) -> None:
    """Promote to admin + active if email matches ADMIN_EMAIL env var."""
    if settings.admin_email and user.email.lower() == settings.admin_email.lower():
        user.status = UserStatus.ACTIVE
        user.role = UserRole.ADMIN


async def create_user(
    session: AsyncSession,
    user: UserCreate,
    initial_status: UserStatus = UserStatus.ACTIVE,
) -> User:
    db_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        status=initial_status,
    )
    _maybe_bootstrap_admin(db_user)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def authenticate(session: AsyncSession, user_data: UserLogin) -> User | None:
    result = await session.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        return None
    if not verify_password(user_data.password, user.password_hash):
        return None
    return user


async def record_login(session: AsyncSession, user: User) -> User:
    now = datetime.now(UTC)
    if user.first_login is None:
        user.first_login = now
    user.last_login = now
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    # noinspection PyTypeChecker
    result = await session.execute(select(User).order_by(User.created_at))  # type: ignore[arg-type]
    return list(result.scalars().all())


async def delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.commit()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def update_user(session: AsyncSession, user: User, data) -> User:
    updates = data.model_dump(exclude_none=True)
    if "username" in updates and updates["username"] != user.username:
        existing = await get_user_by_username(session, updates["username"])
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    for key, value in updates.items():
        setattr(user, key, value)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def approve_user(session: AsyncSession, user: User) -> User:
    user.status = UserStatus.ACTIVE
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def suspend_user(session: AsyncSession, user: User) -> User:
    user.status = UserStatus.BLOCKED
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def set_role(session: AsyncSession, user: User, role: UserRole) -> User:
    user.role = role
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def ensure_admin(session: AsyncSession, email: str) -> None:
    """Startup bootstrap: promote the admin_email user if they already exist."""
    try:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user and (user.status != UserStatus.ACTIVE or user.role != UserRole.ADMIN):
            user.status = UserStatus.ACTIVE
            user.role = UserRole.ADMIN
            session.add(user)
            await session.commit()
            logger.info("admin_bootstrapped", email=email)
    except SQLAlchemyError:
        logger.warning("admin_bootstrap_skipped", email=email)

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import BackgroundTasks, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.passwords import check_password_strength, hash_password, verify_password
from app.models.auth_token import TokenPurpose
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserUpdate,
    VerifyEmailRequest,
)
from app.services import auth_token, email_templates
from app.services import email as email_service
from app.services.base import save_updates
from app.utils.config import settings

logger = structlog.get_logger()

RESET_TOKEN_TTL = timedelta(hours=1)
RESET_COOLDOWN = timedelta(seconds=60)
VERIFY_TOKEN_TTL = timedelta(hours=24)
VERIFY_COOLDOWN = timedelta(seconds=60)


def _maybe_bootstrap_admin(user: User) -> None:
    """Promote to admin + active if email matches ADMIN_EMAIL env var."""
    if settings.admin_email and user.email.lower() == settings.admin_email.strip().lower():
        user.status = UserStatus.ACTIVE
        user.role = UserRole.ADMIN


async def _reject_weak_password(password: str, field: str = "password") -> None:
    # Raised as the same 422 a field validator on the schema's `field` would produce, so clients see no
    # difference; it runs here rather than in the schema because zxcvbn is too slow for the event loop.
    weakness = await run_in_threadpool(check_password_strength, password)
    if weakness:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", field),
                    "msg": f"Value error, {weakness}",
                    "input": password,
                    "ctx": {"error": ValueError(weakness)},
                }
            ]
        )


async def create_user(
    session: AsyncSession,
    user: UserCreate,
    initial_status: UserStatus = UserStatus.ACTIVE,
) -> User:
    await _reject_weak_password(user.password)
    # bcrypt is deliberately slow and CPU-bound; run it in a worker thread so it doesn't stall
    # every other request on the event loop.
    db_user = User(
        email=user.email,
        password_hash=await run_in_threadpool(hash_password, user.password),
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
    if not await run_in_threadpool(verify_password, user_data.password, user.password_hash):
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


async def list_users(session: AsyncSession, status_filter: UserStatus | None = None) -> list[User]:
    query = select(User).order_by(User.created_at)  # type: ignore[arg-type]
    if status_filter is not None:
        query = query.where(User.status == status_filter)
    result = await session.execute(query)
    return list(result.scalars().all())


async def delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.commit()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def update_user(session: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.username is not None and data.username != user.username:
        existing = await get_user_by_username(session, data.username)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    return await save_updates(session, user, data)


async def change_password(session: AsyncSession, user: User, data: ChangePasswordRequest) -> None:
    # 400 rather than 401: the UI treats any 401 as an expired session and prompts a re-login.
    if not user.password_hash or not await run_in_threadpool(
        verify_password, data.current_password, user.password_hash
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    await _reject_weak_password(data.new_password, field="new_password")
    user.password_hash = await run_in_threadpool(hash_password, data.new_password)
    user.token_version += 1  # signs out other devices; the route returns a token for this one
    session.add(user)
    await session.commit()


def _email_link(path: str, raw_token: str) -> str:
    # A fragment, like share links, so the token never reaches nginx access logs or a Referer header
    return f"{settings.app_base_url.rstrip('/')}/{path}#{raw_token}"


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def request_password_reset(
    session: AsyncSession, data: ForgotPasswordRequest, background_tasks: BackgroundTasks
) -> None:
    # The caller answers the same way whatever happens here, so the response doesn't reveal whether the
    # account exists. The email goes out after the response, so its timing doesn't either.
    user = await get_user_by_email(session, data.email)
    if user is None or user.status == UserStatus.BLOCKED:
        return
    if await auth_token.recently_issued(session, user, TokenPurpose.RESET_PASSWORD, RESET_COOLDOWN):
        return
    raw = await auth_token.issue(session, user, TokenPurpose.RESET_PASSWORD, RESET_TOKEN_TTL)
    await session.commit()
    email = email_templates.password_reset(_email_link("reset-password", raw))
    background_tasks.add_task(email_service.send_email, user.email, email.subject, email.text, email.html)


async def reset_password(session: AsyncSession, data: ResetPasswordRequest) -> None:
    # 400 rather than 401: the UI treats any 401 as an expired session and prompts a re-login.
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid or has expired"
    )
    token = await auth_token.find_valid(session, data.token, TokenPurpose.RESET_PASSWORD)
    user = await session.get(User, token.user_id) if token else None
    if token is None or user is None or user.status == UserStatus.BLOCKED:
        raise invalid
    # Before using the token up, so a weak password leaves the link usable for another try
    await _reject_weak_password(data.password, field="password")
    user.password_hash = await run_in_threadpool(hash_password, data.password)
    user.token_version += 1  # revokes every access token issued before the reset
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)  # following the link proves the user controls the inbox
    session.add(user)
    if not await auth_token.consume(session, token):
        await session.rollback()
        raise invalid
    await session.commit()


async def send_verification_email(
    session: AsyncSession, user: User, background_tasks: BackgroundTasks
) -> None:
    raw = await auth_token.issue(session, user, TokenPurpose.VERIFY_EMAIL, VERIFY_TOKEN_TTL)
    await session.commit()
    email = email_templates.verify_email(_email_link("verify-email", raw))
    background_tasks.add_task(email_service.send_email, user.email, email.subject, email.text, email.html)


async def resend_verification(
    session: AsyncSession, data: ResendVerificationRequest, background_tasks: BackgroundTasks
) -> None:
    # Like request_password_reset, the caller answers the same way whatever happens here.
    user = await get_user_by_email(session, data.email)
    if user is None or user.status == UserStatus.BLOCKED or user.email_verified_at is not None:
        return
    if await auth_token.recently_issued(session, user, TokenPurpose.VERIFY_EMAIL, VERIFY_COOLDOWN):
        return
    await send_verification_email(session, user, background_tasks)


async def verify_email(session: AsyncSession, data: VerifyEmailRequest) -> None:
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="This verification link is invalid or has expired"
    )
    token = await auth_token.find_valid(session, data.token, TokenPurpose.VERIFY_EMAIL)
    if token is None:
        # Following the link twice (a mail client prefetching it, a double tap) isn't an error
        used = await auth_token.find_used(session, data.token, TokenPurpose.VERIFY_EMAIL)
        used_by = await session.get(User, used.user_id) if used else None
        if used_by is not None and used_by.email_verified_at is not None:
            return
        raise invalid
    user = await session.get(User, token.user_id)
    if user is None:
        raise invalid
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        session.add(user)
    if not await auth_token.consume(session, token):
        # Another request used the link first; that's fine if it verified the address
        await session.rollback()
        await session.refresh(user)
        if user.email_verified_at is None:
            raise invalid
        return
    await session.commit()


async def mark_email_verified(session: AsyncSession, user: User) -> User:
    user.email_verified_at = datetime.now(UTC)
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
    email = email.strip().lower()
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

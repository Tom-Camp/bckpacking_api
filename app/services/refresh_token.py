import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.refresh_token import RefreshToken
from app.models.user import User, UserStatus
from app.utils.config import settings


def _now() -> datetime:
    # One place to read the clock, so tests can move it
    return datetime.now(UTC)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _add(session: AsyncSession, user: User, now: datetime) -> str:
    raw = secrets.token_urlsafe(32)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash(raw),
            token_version=user.token_version,
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
    )
    return raw


async def issue(session: AsyncSession, user: User) -> str:
    """Store a new refresh token for the user and return the raw value, which only the cookie carries."""
    raw = _add(session, user, _now())
    await session.commit()
    return raw


async def rotate(session: AsyncSession, raw: str) -> tuple[User, str] | None:
    """Exchange a refresh token for a successor. None if it's unknown, expired, revoked, issued before the
    user's latest password change or reset (its token_version is stale), or was rotated longer ago than the
    grace window.

    A rotated token stays usable during the grace window, and each use issues another successor, so two tabs
    refreshing at once, or a response lost in transit, doesn't sign the user out. Each successor gets a fresh
    lifetime, so the session slides while it's in use.

    Raises 403 for a blocked user holding an otherwise valid token, without touching the token, so a restored
    user can refresh again. A revoked or stale token gets None (401) whatever the user's status.
    """
    now = _now()
    grace = timedelta(seconds=settings.refresh_rotation_grace_seconds)
    # Times are compared in SQL: SQLite hands back naive datetimes, which can't be compared to aware ones.
    result = await session.execute(
        select(RefreshToken).where(
            col(RefreshToken.token_hash) == _hash(raw),
            col(RefreshToken.revoked_at).is_(None),
            col(RefreshToken.expires_at) > now,
            or_(col(RefreshToken.rotated_at).is_(None), col(RefreshToken.rotated_at) > now - grace),
        )
    )
    token = result.scalar_one_or_none()
    user = await session.get(User, token.user_id) if token else None
    if token is None or user is None or token.token_version != user.token_version:
        return None
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    if token.rotated_at is None:
        token.rotated_at = now
        session.add(token)
    new_raw = _add(session, user, now)
    await session.commit()
    return user, new_raw


async def revoke(session: AsyncSession, raw: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(col(RefreshToken.token_hash) == _hash(raw), col(RefreshToken.revoked_at).is_(None))
        .values(revoked_at=_now())
    )
    await session.commit()


async def revoke_all(session: AsyncSession, user: User) -> None:
    """Revoke every refresh token the user holds. Doesn't commit, so it commits with the caller's change."""
    await session.execute(
        update(RefreshToken)
        .where(col(RefreshToken.user_id) == user.id, col(RefreshToken.revoked_at).is_(None))
        .values(revoked_at=_now())
    )

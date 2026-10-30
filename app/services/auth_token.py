import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.auth_token import AuthToken, TokenPurpose
from app.models.user import User


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue(session: AsyncSession, user: User, purpose: TokenPurpose, ttl: timedelta) -> str:
    """Store a new token and return the raw value, which only the email carries. Doesn't commit.

    The user's earlier unused tokens of this purpose are marked used, so only the newest link works.
    """
    now = datetime.now(UTC)
    await session.execute(
        update(AuthToken)
        .where(
            col(AuthToken.user_id) == user.id,
            col(AuthToken.purpose) == purpose,
            col(AuthToken.used_at).is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    session.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=_hash(raw), expires_at=now + ttl))
    return raw


async def find_valid(session: AsyncSession, raw: str, purpose: TokenPurpose) -> AuthToken | None:
    """The unused, unexpired token of this purpose, without using it up (see consume)."""
    # Expiry is compared in SQL: SQLite hands back naive datetimes, which can't be compared to aware ones.
    result = await session.execute(
        select(AuthToken).where(
            col(AuthToken.token_hash) == _hash(raw),
            col(AuthToken.purpose) == purpose,
            col(AuthToken.used_at).is_(None),
            col(AuthToken.expires_at) > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def consume(session: AsyncSession, token: AuthToken) -> bool:
    """Mark the token used, unless a concurrent request already did. Doesn't commit, so the caller's change
    and the token's used_at commit together."""
    result = await session.execute(
        update(AuthToken)
        .where(col(AuthToken.id) == token.id, col(AuthToken.used_at).is_(None))
        .values(used_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def recently_issued(
    session: AsyncSession, user: User, purpose: TokenPurpose, within: timedelta
) -> bool:
    result = await session.execute(
        select(AuthToken.id)
        .where(
            col(AuthToken.user_id) == user.id,
            col(AuthToken.purpose) == purpose,
            col(AuthToken.created_at) > datetime.now(UTC) - within,
        )
        .limit(1)
    )
    return result.first() is not None

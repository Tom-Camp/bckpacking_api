import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.models.user import User
from app.utils.config import settings


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[uuid.UUID, int]:
    """The token's user id and token version (see User.token_version)."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("Token 'sub' claim is missing or not a valid UUID") from exc
    version = payload.get("ver")
    # type() rather than isinstance(): a JSON true would otherwise pass as 1
    if type(version) is not int:
        raise jwt.InvalidTokenError("Token 'ver' claim is missing or not an integer")
    return user_id, version

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.utils.config import settings


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("Token 'sub' claim is missing or not a valid UUID") from exc

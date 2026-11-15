from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.models.base import ModelBase


class RefreshToken(ModelBase, table=True):
    """A long-lived session token, held by the client in an httpOnly cookie (see services/refresh_token).
    Only its sha256 is stored."""

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    token_hash: str = Field(unique=True, index=True)
    # User.token_version when issued. A password change or reset bumps the user's, so a token issued by a
    # refresh that raced the change (after its revoke_all) still stops working.
    token_version: int
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    # Set when the token is first exchanged for a successor; it stays usable for a short grace window after
    rotated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

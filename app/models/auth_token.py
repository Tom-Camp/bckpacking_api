from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.models.base import ModelBase, enum_field


class TokenPurpose(StrEnum):
    RESET_PASSWORD = "reset_password"  # noqa: S105 - a token purpose, not a secret


class AuthToken(ModelBase, table=True):
    """A single-use token emailed to a user (see services/auth_token). Only its sha256 is stored."""

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    purpose: TokenPurpose = enum_field(TokenPurpose, TokenPurpose.RESET_PASSWORD)
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

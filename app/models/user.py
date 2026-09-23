from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship

from app.models.base import ModelBase, enum_field
from app.models.trip import Trip


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    UNAUTHENTICATED = "unauthenticated"


class User(ModelBase, table=True):
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    first_name: str | None = None
    last_name: str | None = None
    picture: str | None = None
    body_weight_g: float | None = None
    status: UserStatus = enum_field(UserStatus, UserStatus.ACTIVE)
    role: UserRole = enum_field(UserRole, UserRole.USER)
    first_login: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_login: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    trips: list[Trip] = Relationship(
        back_populates="user", passive_deletes=True, sa_relationship_kwargs={"lazy": "raise_on_sql"}
    )

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field

from app.models.base import ModelBase


class UserStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    UNAUTHENTICATED = "unauthenticated"


class User(ModelBase, table=True):
    email: str = Field(unique=True, index=True)
    username: str | None = Field(default=None, unique=True, index=True)
    password_hash: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        sa_column=Column(
            SAEnum(UserStatus, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        ),
    )
    role: UserRole = Field(
        default=UserRole.USER,
        sa_column=Column(
            SAEnum(UserRole, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        ),
    )
    first_login: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_login: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

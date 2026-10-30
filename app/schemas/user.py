import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import Unit, UserRole, UserStatus
from app.schemas.base import UpdateSchema

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,30}$")

_MAX_PASSWORD_BYTES = 72  # bcrypt truncates/rejects beyond this


def _validate_password_length(v: str) -> str:
    # The zxcvbn strength check is too slow for the event loop, so it runs in services/user.create_user.
    if len(v.encode()) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes")
    return v


def _normalize_email(v: str) -> str:
    # EmailStr lowercases only the domain; emails are unique and matched case-insensitively
    return v.strip().lower()


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: str
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_length(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is not None and not _USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 characters: letters, digits, _ or -")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class UserUpdate(UpdateSchema):
    non_nullable = frozenset({"username", "measurements"})

    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    picture: str | None = None
    body_weight_g: float | None = Field(default=None, gt=0)
    measurements: Unit | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is not None and not _USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 characters: letters, digits, _ or -")
        return v


class SetRoleRequest(BaseModel):
    role: UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    first_name: str | None = None
    last_name: str | None = None
    picture: str | None = None
    body_weight_g: float | None = None
    measurements: Unit
    status: UserStatus
    role: UserRole
    first_login: datetime | None = None
    last_login: datetime | None = None
    email_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    # Only the length is checked here; services/user.change_password rejects weak passwords off the event loop.
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_length(v)


class ResetPasswordRequest(BaseModel):
    # Only the length is checked here. The service that applies a reset must also reject weak passwords
    # (see services/user._reject_weak_password), off the event loop.
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_length(v)

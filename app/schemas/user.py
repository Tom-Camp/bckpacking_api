import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from zxcvbn import zxcvbn

from app.models.user import UserRole, UserStatus

_USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,30}$")

_MIN_ZXCVBN_SCORE = 3
_MAX_PASSWORD_BYTES = 72  # bcrypt truncates/rejects beyond this


def _validate_password_strength(v: str) -> str:
    if len(v.encode()) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes")
    result = zxcvbn(v)
    if result["score"] < _MIN_ZXCVBN_SCORE:
        warning = result["feedback"].get("warning")
        suggestions = result["feedback"].get("suggestions", [])
        message = warning or (suggestions[0] if suggestions else "Password is too weak")
        raise ValueError(message)
    return v


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: str
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is not None and not _USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 characters: lowercase letters, digits, _ or -")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    picture: str | None = None

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
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    picture: str | None = None
    status: UserStatus
    role: UserRole
    first_login: datetime | None = None
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

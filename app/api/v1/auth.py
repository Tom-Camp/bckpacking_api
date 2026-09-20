import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import create_access_token
from app.db import get_session
from app.models.user import UserStatus
from app.schemas.user import TokenResponse, UserCreate, UserLogin
from app.services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await user_service.create_user(session=session, user=user, initial_status=UserStatus.ACTIVE)
    except IntegrityError as exc:
        detail = (
            "Username already taken" if "username" in str(exc.orig).lower() else "Email already registered"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None

    return {"message": "Registration successful."}


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await user_service.authenticate(session=session, user_data=data)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.status == UserStatus.BLOCKED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    await user_service.record_login(session, user)
    return TokenResponse(access_token=create_access_token(user.id))

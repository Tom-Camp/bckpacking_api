import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_active_user
from app.db import get_session
from app.models.gear import GearItem
from app.models.user import User
from app.schemas.gear import GearItemCreate, GearItemRead, GearItemUpdate
from app.services import gear as gear_service

router = APIRouter(prefix="/gear", tags=["gear"])


async def get_owned_gear_item(
    item_id: uuid.UUID,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> GearItem:
    item = await gear_service.get_item(session, user.id, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gear item not found")
    return item


@router.post("", response_model=GearItemRead, status_code=status.HTTP_201_CREATED)
async def create_gear_item(
    data: GearItemCreate,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> GearItemRead:
    item = await gear_service.create_item(session, user.id, data)
    return GearItemRead.model_validate(item)


@router.get("", response_model=list[GearItemRead])
async def list_gear_items(
    include_archived: bool = False,
    user: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_session),
) -> list[GearItemRead]:
    items = await gear_service.list_items(session, user.id, include_archived=include_archived)
    return [GearItemRead.model_validate(i) for i in items]


@router.get("/{item_id}", response_model=GearItemRead)
async def get_gear_item(item: GearItem = Depends(get_owned_gear_item)) -> GearItemRead:
    return GearItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=GearItemRead)
async def update_gear_item(
    data: GearItemUpdate,
    item: GearItem = Depends(get_owned_gear_item),
    session: AsyncSession = Depends(get_session),
) -> GearItemRead:
    item = await gear_service.update_item(session, item, data)
    return GearItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_gear_item(
    item: GearItem = Depends(get_owned_gear_item),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Archive the item: it leaves the closet list but stays on trips that already pack it."""
    await gear_service.archive_item(session, item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{item_id}/restore", response_model=GearItemRead)
async def restore_gear_item(
    item: GearItem = Depends(get_owned_gear_item),
    session: AsyncSession = Depends(get_session),
) -> GearItemRead:
    item = await gear_service.restore_item(session, item)
    return GearItemRead.model_validate(item)

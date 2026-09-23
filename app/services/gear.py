import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.gear import GearItem
from app.schemas.gear import GearItemCreate, GearItemUpdate
from app.services.base import save_updates


async def create_item(session: AsyncSession, user_id: uuid.UUID, data: GearItemCreate) -> GearItem:
    item = GearItem(user_id=user_id, **data.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def list_items(
    session: AsyncSession, user_id: uuid.UUID, include_archived: bool = False
) -> list[GearItem]:
    query = select(GearItem).where(GearItem.user_id == user_id)
    if not include_archived:
        query = query.where(col(GearItem.archived_at).is_(None))
    result = await session.execute(query.order_by(col(GearItem.category), col(GearItem.name)))
    return list(result.scalars().all())


async def get_item(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> GearItem | None:
    # Scoped to the owner: another user's item is indistinguishable from a missing one.
    result = await session.execute(
        select(GearItem).where(GearItem.id == item_id, GearItem.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_item(session: AsyncSession, item: GearItem, data: GearItemUpdate) -> GearItem:
    return await save_updates(session, item, data)


async def archive_item(session: AsyncSession, item: GearItem) -> None:
    if item.archived_at is None:
        item.archived_at = datetime.now(UTC)
        session.add(item)
        await session.commit()


async def restore_item(session: AsyncSession, item: GearItem) -> GearItem:
    item.archived_at = None
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.schemas.base import UpdateSchema


async def save_updates[T: SQLModel](session: AsyncSession, obj: T, data: UpdateSchema) -> T:
    # exclude_unset (not exclude_none): an omitted field is left alone, an explicit null clears it.
    # UpdateSchema already rejected nulls for NOT NULL columns.
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj

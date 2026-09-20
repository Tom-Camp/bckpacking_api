from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, String, event, func
from sqlalchemy.orm import class_mapper
from sqlalchemy.sql.type_api import TypeDecorator
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_string_column(col_type: object) -> bool:
    if isinstance(col_type, String):
        return True
    if isinstance(col_type, TypeDecorator) and isinstance(col_type.impl_instance, String):
        return True
    return False


def _strip_strings(target: "ModelBase") -> None:
    mapper = class_mapper(type(target))
    for col in mapper.columns:
        if _is_string_column(col.type):
            value = getattr(target, col.key, None)
            if isinstance(value, str):
                setattr(target, col.key, value.strip())


class ModelBase(SQLModel):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
        ),
    )


@event.listens_for(ModelBase, "before_insert", propagate=True)
@event.listens_for(ModelBase, "before_update", propagate=True)
def _strip_on_write(_mapper, _connection, target: ModelBase) -> None:
    _strip_strings(target)

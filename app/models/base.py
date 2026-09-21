from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, event, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import class_mapper
from sqlalchemy.sql.type_api import TypeDecorator, TypeEngine
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def enum_field(enum_cls: type[Enum], default: Enum) -> Any:
    return Field(
        default=default,
        sa_column=Column(SAEnum(enum_cls, values_callable=lambda x: [e.value for e in x]), nullable=False),
    )


def _is_string_column(col_type: object) -> bool:
    if isinstance(col_type, TypeDecorator):
        col_type = col_type.impl_instance
    if not isinstance(col_type, TypeEngine):
        return False
    try:
        return col_type.python_type is str
    except NotImplementedError:
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
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": func.now(), "onupdate": _utcnow},
    )


@event.listens_for(ModelBase, "before_insert", propagate=True)
@event.listens_for(ModelBase, "before_update", propagate=True)
def _strip_on_write(_mapper, _connection, target: ModelBase) -> None:
    _strip_strings(target)

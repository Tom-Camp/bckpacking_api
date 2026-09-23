from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import field_validator
from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.models.base import ModelBase, enum_field


class GearKind(StrEnum):
    BASE = "base"
    WORN = "worn"  # excluded from pack weight
    CONSUMABLE = "consumable"  # in pack weight, excluded from base weight


class GearItem(ModelBase, table=True):
    """A piece of gear in a user's closet, shared by every trip that packs it (via TripGear)."""

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str
    category: str
    weight_g: float = Field(default=0.0)
    kind: GearKind = enum_field(GearKind, GearKind.BASE)
    notes: str | None = Field(default=None)
    # Items are archived rather than deleted so trips that used them keep their gear list.
    archived_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    @field_validator("category", mode="before")
    @classmethod
    def lowercase_category(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower()
        return v

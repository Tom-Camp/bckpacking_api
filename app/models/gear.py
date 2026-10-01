from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from app.models.base import ModelBase, enum_field


class GearCategory(StrEnum):
    CLOTHING = "clothing"
    COOKING_WATER = "cooking_water"
    MISCELLANEOUS = "misc"
    NAVIGATION_SAFETY = "navigation_safety"
    SHELTER = "shelter"
    SLEEP = "sleep"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS: dict[GearCategory, str] = {
    GearCategory.CLOTHING: "Clothing",
    GearCategory.COOKING_WATER: "Cooking & Water",
    GearCategory.MISCELLANEOUS: "Miscellaneous",
    GearCategory.NAVIGATION_SAFETY: "Navigation & Safety",
    GearCategory.SHELTER: "Shelter",
    GearCategory.SLEEP: "Sleep",
}


class GearKind(StrEnum):
    BASE = "base"
    WORN = "worn"  # excluded from pack weight
    CONSUMABLE = "consumable"  # in pack weight, excluded from base weight


class GearItem(ModelBase, table=True):
    """A piece of gear in a user's closet, shared by every trip that packs it (via TripGear)."""

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str
    category: GearCategory = enum_field(GearCategory, GearCategory.MISCELLANEOUS)
    weight_g: float = Field(default=0.0)
    kind: GearKind = enum_field(GearKind, GearKind.BASE)
    notes: str | None = Field(default=None)
    # Items are archived rather than deleted so trips that used them keep their gear list.
    archived_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

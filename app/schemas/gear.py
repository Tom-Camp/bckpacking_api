import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.gear import GearCategory, GearKind
from app.schemas.base import UpdateSchema


def _lowercase(v: str | None) -> str | None:
    return v.lower() if isinstance(v, str) else v


class GearItemCreate(BaseModel):
    name: str
    category: GearCategory = GearCategory.MISCELLANEOUS
    weight_g: float = Field(default=0.0, ge=0)
    kind: GearKind = GearKind.BASE
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str) -> str:
        return v.lower()


class GearItemUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "category", "weight_g", "kind"})

    name: str | None = None
    category: GearCategory | None = None
    weight_g: float | None = Field(default=None, ge=0)
    kind: GearKind | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str | None) -> str | None:
        return _lowercase(v)


class GearItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: GearCategory
    weight_g: float
    kind: GearKind
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    def status_label(self) -> str:
        return self.category.label

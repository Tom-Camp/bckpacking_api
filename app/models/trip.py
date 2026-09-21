from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql.type_api import TypeDecorator
from sqlmodel import Field, Relationship

from app.models.base import ModelBase, enum_field

if TYPE_CHECKING:
    from app.models.user import User


CHECKLIST_ITEMS = (
    "water_sources",
    "resupply_points",
    "shuttle_scheduled",
    "weather_checked",
    "cell_coverage",
    "offline_map",
    "fire_restrictions",
    "route_shared",
)


class ChecklistItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    checked: bool = False
    details: str | None = None


class _ChecklistJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(
        self, value: dict[str, ChecklistItem] | None, dialect: object
    ) -> dict[str, dict[str, object]] | None:
        if value is None:
            return None
        return {key: item.model_dump() for key, item in value.items()}

    def process_result_value(
        self, value: dict[str, object] | None, dialect: object
    ) -> dict[str, ChecklistItem]:
        if value is None:
            return {}
        return {key: ChecklistItem.model_validate(item) for key, item in value.items()}


def _default_checklist() -> dict[str, ChecklistItem]:
    return {item: ChecklistItem() for item in CHECKLIST_ITEMS}


class TripType(str, Enum):
    LOOP = "loop"
    OUT_AND_BACK = "out-and-back"
    POINT_TO_POINT = "point-to-point"


class Meal(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class Unit(str, Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


class TripFood(ModelBase, table=True):
    day: str
    name: str
    meal_type: Meal = enum_field(Meal, Meal.BREAKFAST)
    weight: float
    calories: int
    planner_id: UUID = Field(foreign_key="foodplanner.id", ondelete="CASCADE")
    planner: "FoodPlanner" = Relationship(
        back_populates="food", sa_relationship_kwargs={"lazy": "raise_on_sql"}
    )


class FoodPlanner(ModelBase, table=True):
    target_calories: int = Field(default=0)
    target_food_weight: float = Field(default=0)
    trip_id: UUID = Field(foreign_key="trip.id", unique=True, ondelete="CASCADE")
    food: list[TripFood] = Relationship(
        back_populates="planner", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )
    trip: "Trip" = Relationship(back_populates="food_plan", sa_relationship_kwargs={"lazy": "raise_on_sql"})


class Gear(ModelBase, table=True):
    category: str
    weight: float = Field(default=0.0)
    quantity: int = Field(default=0)
    notes: str | None = Field(default=None)
    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    trip: "Trip" = Relationship(back_populates="gear_list", sa_relationship_kwargs={"lazy": "raise_on_sql"})

    @field_validator("category", mode="before")
    @classmethod
    def lowercase_category(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower()
        return v


class Trip(ModelBase, table=True):
    name: str = Field(...)
    description: str | None = Field(default=None)
    measurements: Unit = enum_field(Unit, Unit.IMPERIAL)
    trip_type: TripType = enum_field(TripType, TripType.LOOP)
    start_date: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    end_date: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    start_trailhead: str | None = Field(default=None)
    end_trailhead: str | None = Field(default=None)
    total_distance: int
    elevation_gain: int | None = Field(default=None)
    map_link: str | None = Field(default=None)
    emergency_contact: str | None = Field(default=None)
    permit_required: bool = Field(default=False)
    permit_details: str | None = Field(default=None)
    checklist: dict[str, ChecklistItem] = Field(
        default_factory=_default_checklist,
        sa_column=Column(MutableDict.as_mutable(_ChecklistJSON), nullable=False),
        description="Pre-trip safety checklist keyed by item name (see CHECKLIST_ITEMS)",
    )

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    user: "User" = Relationship(back_populates="trips", sa_relationship_kwargs={"lazy": "raise_on_sql"})
    food_plan: Optional["FoodPlanner"] = Relationship(
        back_populates="trip", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )
    gear_list: list[Gear] = Relationship(
        back_populates="trip", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )

    def set_checklist_item(self, key: str, item: ChecklistItem) -> None:
        # Whole-attribute reassignment is always tracked; in-place `checklist[key] = ...`
        # is not, until the object has round-tripped through the DB at least once.
        self.checklist = {**self.checklist, key: item}

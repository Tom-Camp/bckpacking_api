from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from pydantic import field_validator
from sqlalchemy import Column, DateTime, UniqueConstraint, event
from sqlmodel import Field, Relationship

from app.models.base import ModelBase, enum_field

if TYPE_CHECKING:
    from app.models.user import User


class ChecklistItemKey(str, Enum):
    WATER_SOURCES = "water_sources"
    RESUPPLY_POINTS = "resupply_points"
    SHUTTLE_SCHEDULED = "shuttle_scheduled"
    WEATHER_CHECKED = "weather_checked"
    CELL_COVERAGE = "cell_coverage"
    OFFLINE_MAP = "offline_map"
    FIRE_RESTRICTIONS = "fire_restrictions"
    ROUTE_SHARED = "route_shared"


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


class TripChecklistItem(ModelBase, table=True):
    __table_args__ = (UniqueConstraint("trip_id", "item"),)

    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    item: ChecklistItemKey = enum_field(ChecklistItemKey, ChecklistItemKey.WATER_SOURCES)
    checked: bool = Field(default=False)
    details: str | None = Field(default=None)
    trip: "Trip" = Relationship(
        back_populates="checklist_items", sa_relationship_kwargs={"lazy": "raise_on_sql"}
    )


class TripNote(ModelBase, table=True):
    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    content: str
    trip: "Trip" = Relationship(back_populates="notes", sa_relationship_kwargs={"lazy": "raise_on_sql"})


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

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    user: "User" = Relationship(back_populates="trips", sa_relationship_kwargs={"lazy": "raise_on_sql"})
    food_plan: Optional["FoodPlanner"] = Relationship(
        back_populates="trip",
        passive_deletes=True,
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    gear_list: list[Gear] = Relationship(
        back_populates="trip", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )
    checklist_items: list[TripChecklistItem] = Relationship(
        back_populates="trip",
        passive_deletes=True,
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    notes: list[TripNote] = Relationship(
        back_populates="trip", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )


@event.listens_for(Trip, "init")
def _seed_checklist_items(_target: Trip, _args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    kwargs.setdefault("checklist_items", [TripChecklistItem(item=key) for key in ChecklistItemKey])


@event.listens_for(Trip, "init")
def _seed_food_planner(_target: Trip, _args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    kwargs.setdefault("food_plan", FoodPlanner())

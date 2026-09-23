from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, ForeignKey, UniqueConstraint, event
from sqlmodel import Field, Relationship

from app.models.base import ModelBase, enum_field
from app.models.gear import GearItem

if TYPE_CHECKING:
    from app.models.user import User


class ChecklistItemKey(StrEnum):
    PERMIT_REQUIRED = "permit_required"
    WATER_SOURCES = "water_sources"
    RESUPPLY_POINTS = "resupply_points"
    SHUTTLE_SCHEDULED = "shuttle_scheduled"
    WEATHER_CHECKED = "weather_checked"
    CELL_COVERAGE = "cell_coverage"
    OFFLINE_MAP = "offline_map"
    FIRE_RESTRICTIONS = "fire_restrictions"
    ROUTE_SHARED = "route_shared"


class TripType(StrEnum):
    LOOP = "loop"
    OUT_AND_BACK = "out-and-back"
    POINT_TO_POINT = "point-to-point"


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class TripFood(ModelBase, table=True):
    # 1-based trip day; the frontend renders "Day 1 (Aug 26)" from the trip's start_date.
    day: int
    name: str
    meal_type: Meal = enum_field(Meal, Meal.BREAKFAST)
    # weight_g and kcal are per serving; totals are servings x value.
    servings: float = Field(default=1)
    weight_g: float
    kcal: int
    planner_id: UUID = Field(foreign_key="foodplanner.id", ondelete="CASCADE")
    planner: FoodPlanner = Relationship(
        back_populates="food", sa_relationship_kwargs={"lazy": "raise_on_sql"}
    )


class FoodPlanner(ModelBase, table=True):
    # Defaults from the trip-planner template: 2700 kcal and 1.75 lb (~794 g) of food per day.
    target_kcal_per_day: int = Field(default=2700)
    target_food_g_per_day: float = Field(default=794)
    trip_id: UUID = Field(foreign_key="trip.id", unique=True, ondelete="CASCADE")
    food: list[TripFood] = Relationship(
        back_populates="planner", passive_deletes=True, sa_relationship_kwargs={"lazy": "selectin"}
    )
    trip: Trip = Relationship(back_populates="food_plan", sa_relationship_kwargs={"lazy": "raise_on_sql"})


class TripGear(ModelBase, table=True):
    """A closet GearItem packed for a trip. Weight/name/kind live on the item, so edits apply to every trip."""

    __table_args__ = (UniqueConstraint("trip_id", "gear_item_id"),)

    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    # No ON DELETE: closet items are archived, never deleted, while a trip still uses them. Deferred to
    # commit so deleting a user works: Postgres checks a non-deferred FK as soon as the user -> gearitem
    # cascade runs, before the user -> trip -> tripgear cascade has removed the rows pointing at it.
    gear_item_id: UUID = Field(
        sa_column=Column(ForeignKey("gearitem.id", deferrable=True, initially="DEFERRED"), nullable=False)
    )
    quantity: int = Field(default=1)
    packed: bool = Field(default=False)
    gear_item: GearItem = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    trip: Trip = Relationship(back_populates="gear_list", sa_relationship_kwargs={"lazy": "raise_on_sql"})


class TripChecklistItem(ModelBase, table=True):
    __table_args__ = (UniqueConstraint("trip_id", "item"),)

    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    item: ChecklistItemKey = enum_field(ChecklistItemKey, ChecklistItemKey.WATER_SOURCES)
    checked: bool = Field(default=False)
    details: str | None = Field(default=None)
    trip: Trip = Relationship(
        back_populates="checklist_items", sa_relationship_kwargs={"lazy": "raise_on_sql"}
    )


class TripNote(ModelBase, table=True):
    trip_id: UUID = Field(foreign_key="trip.id", ondelete="CASCADE")
    content: str
    trip: Trip = Relationship(back_populates="notes", sa_relationship_kwargs={"lazy": "raise_on_sql"})


class Trip(ModelBase, table=True):
    # Backstop for the schema/service validation; NULLs pass, so either date may be unset.
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_trip_end_date_after_start_date"),)

    name: str = Field(...)
    description: str | None = Field(default=None)
    area: str | None = Field(default=None)  # e.g. "Pisgah"
    trip_type: TripType = enum_field(TripType, TripType.LOOP)
    # Calendar dates, not instants: a trip starts on "Aug 26" wherever the viewer is.
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    start_trailhead: str | None = Field(default=None)
    end_trailhead: str | None = Field(default=None)
    # Canonical units (API_GAPS 2.1): meters; the frontend converts for display.
    total_distance_m: float | None = Field(default=None)
    elevation_gain_m: float | None = Field(default=None)
    water_carry_l: float = Field(default=0)
    map_link: str | None = Field(default=None)
    emergency_contact: str | None = Field(default=None)

    user_id: UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    user: User = Relationship(back_populates="trips", sa_relationship_kwargs={"lazy": "raise_on_sql"})
    food_plan: FoodPlanner | None = Relationship(
        back_populates="trip",
        passive_deletes=True,
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    gear_list: list[TripGear] = Relationship(
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

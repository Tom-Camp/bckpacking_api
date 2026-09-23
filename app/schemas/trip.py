import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.trip import ChecklistItemKey, Meal, TripType, Unit
from app.schemas.base import UpdateSchema


def _lowercase_category(v: str | None) -> str | None:
    return v.lower() if isinstance(v, str) else v


def check_date_order(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")


class TripCreate(BaseModel):
    name: str
    description: str | None = None
    measurements: Unit = Unit.IMPERIAL
    trip_type: TripType = TripType.LOOP
    start_date: date | None = None
    end_date: date | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance_m: float | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = Field(default=None, ge=0)
    map_link: str | None = None
    emergency_contact: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_not_before_start_date(cls, v: date | None, info: ValidationInfo) -> date | None:
        check_date_order(info.data.get("start_date"), v)
        return v


class TripUpdate(UpdateSchema):
    non_nullable = frozenset({"name", "measurements", "trip_type"})

    name: str | None = None
    description: str | None = None
    measurements: Unit | None = None
    trip_type: TripType | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance_m: float | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = Field(default=None, ge=0)
    map_link: str | None = None
    emergency_contact: str | None = None


class GearCreate(BaseModel):
    gear_name: str
    category: str
    weight: float = Field(default=0.0, ge=0)
    quantity: int = Field(default=0, ge=0)
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str) -> str:
        return v.lower()


class GearUpdate(UpdateSchema):
    non_nullable = frozenset({"gear_name", "category", "weight", "quantity"})

    gear_name: str | None = None
    category: str | None = None
    weight: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str | None) -> str | None:
        return _lowercase_category(v)


class GearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gear_name: str
    category: str
    weight: float
    quantity: int
    notes: str | None
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TripNoteCreate(BaseModel):
    content: str


class TripNoteUpdate(UpdateSchema):
    non_nullable = frozenset({"content"})

    content: str | None = None


class TripNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChecklistItemUpdate(UpdateSchema):
    non_nullable = frozenset({"checked"})

    checked: bool | None = None
    details: str | None = None


class ChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item: ChecklistItemKey
    checked: bool
    details: str | None
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TripFoodCreate(BaseModel):
    day: str
    name: str
    meal_type: Meal = Meal.BREAKFAST
    weight: float = Field(ge=0)
    calories: int = Field(ge=0)


class TripFoodUpdate(UpdateSchema):
    non_nullable = frozenset({"day", "name", "meal_type", "weight", "calories"})

    day: str | None = None
    name: str | None = None
    meal_type: Meal | None = None
    weight: float | None = Field(default=None, ge=0)
    calories: int | None = Field(default=None, ge=0)


class TripFoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day: str
    name: str
    meal_type: Meal
    weight: float
    calories: int
    planner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FoodPlannerUpdate(UpdateSchema):
    non_nullable = frozenset({"target_calories", "target_food_weight"})

    target_calories: int | None = Field(default=None, ge=0)
    target_food_weight: float | None = Field(default=None, ge=0)


class FoodPlannerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_calories: int
    target_food_weight: float
    trip_id: uuid.UUID
    food: list[TripFoodRead]
    created_at: datetime
    updated_at: datetime


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    measurements: Unit
    trip_type: TripType
    start_date: date | None
    end_date: date | None
    start_trailhead: str | None
    end_trailhead: str | None
    total_distance_m: float | None
    elevation_gain_m: float | None
    map_link: str | None
    emergency_contact: str | None
    food_plan: FoodPlannerRead | None
    gear_list: list[GearRead]
    checklist_items: list[ChecklistItemRead]
    notes: list[TripNoteRead]
    created_at: datetime
    updated_at: datetime

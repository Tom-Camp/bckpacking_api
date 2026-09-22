import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.trip import ChecklistItemKey, Meal, TripType, Unit


def _lowercase_category(v: str | None) -> str | None:
    return v.lower() if isinstance(v, str) else v


class TripCreate(BaseModel):
    name: str
    description: str | None = None
    measurements: Unit = Unit.IMPERIAL
    trip_type: TripType = TripType.LOOP
    start_date: datetime | None = None
    end_date: datetime | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance: int
    elevation_gain: int | None = None
    map_link: str | None = None
    emergency_contact: str | None = None
    permit_required: bool = False
    permit_details: str | None = None


class TripUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    measurements: Unit | None = None
    trip_type: TripType | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance: int | None = None
    elevation_gain: int | None = None
    map_link: str | None = None
    emergency_contact: str | None = None
    permit_required: bool | None = None
    permit_details: str | None = None


class GearCreate(BaseModel):
    category: str
    weight: float = 0.0
    quantity: int = 0
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str) -> str:
        return v.lower()


class GearUpdate(BaseModel):
    category: str | None = None
    weight: float | None = None
    quantity: int | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, v: str | None) -> str | None:
        return _lowercase_category(v)


class GearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    weight: float
    quantity: int
    notes: str | None
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TripNoteCreate(BaseModel):
    content: str


class TripNoteUpdate(BaseModel):
    content: str | None = None


class TripNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChecklistItemUpdate(BaseModel):
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
    weight: float
    calories: int


class TripFoodUpdate(BaseModel):
    day: str | None = None
    name: str | None = None
    meal_type: Meal | None = None
    weight: float | None = None
    calories: int | None = None


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


class FoodPlannerUpdate(BaseModel):
    target_calories: int | None = None
    target_food_weight: float | None = None


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
    start_date: datetime | None
    end_date: datetime | None
    start_trailhead: str | None
    end_trailhead: str | None
    total_distance: int
    elevation_gain: int | None
    map_link: str | None
    emergency_contact: str | None
    permit_required: bool
    permit_details: str | None
    food_plan: FoodPlannerRead | None
    gear_list: list[GearRead]
    checklist_items: list[ChecklistItemRead]
    notes: list[TripNoteRead]
    created_at: datetime
    updated_at: datetime

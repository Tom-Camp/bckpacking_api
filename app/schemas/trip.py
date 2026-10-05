import uuid
from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, computed_field, field_validator

from app.models.gear import GearCategory, GearKind
from app.models.trip import ChecklistItemKey, ChecklistStatus, Meal, Trip, TripType
from app.schemas.base import UpdateSchema
from app.schemas.gear import GearItemRead


def check_date_order(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")


class TripCreate(BaseModel):
    name: str
    description: str | None = None
    area: str | None = None
    trip_type: TripType = TripType.LOOP
    start_date: date | None = None
    end_date: date | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance_m: float | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = Field(default=None, ge=0)
    water_carry_l: float = Field(default=0, ge=0)
    map_link: str | None = None
    emergency_contact: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_not_before_start_date(cls, v: date | None, info: ValidationInfo) -> date | None:
        check_date_order(info.data.get("start_date"), v)
        return v


class TripUpdate(UpdateSchema):
    non_nullable = frozenset(
        {
            "name",
            "trip_type",
            "water_carry_l",
            "share_gear",
            "share_food",
            "share_checklist",
            "share_emergency_contact",
        }
    )

    name: str | None = None
    description: str | None = None
    area: str | None = None
    trip_type: TripType | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_trailhead: str | None = None
    end_trailhead: str | None = None
    total_distance_m: float | None = Field(default=None, ge=0)
    elevation_gain_m: float | None = Field(default=None, ge=0)
    water_carry_l: float | None = Field(default=None, ge=0)
    map_link: str | None = None
    emergency_contact: str | None = None
    share_gear: bool | None = None
    share_food: bool | None = None
    share_checklist: bool | None = None
    share_emergency_contact: bool | None = None


class TripGearCreate(BaseModel):
    gear_item_id: uuid.UUID
    quantity: int = Field(default=1, ge=1)
    packed: bool = False


class TripGearUpdate(UpdateSchema):
    non_nullable = frozenset({"quantity", "packed"})

    quantity: int | None = Field(default=None, ge=1)
    packed: bool | None = None


class TripGearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    gear_item: GearItemRead
    quantity: int
    packed: bool
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
    non_nullable = frozenset({"status"})

    status: ChecklistStatus | None = None
    details: str | None = None


class ChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item: ChecklistItemKey
    status: ChecklistStatus
    details: str | None
    trip_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TripFoodCreate(BaseModel):
    day: int = Field(ge=1)
    name: str
    meal_type: Meal = Meal.BREAKFAST
    servings: float = Field(default=1, gt=0)
    weight_g: float = Field(ge=0)
    kcal: int = Field(ge=0)


class TripFoodUpdate(UpdateSchema):
    non_nullable = frozenset({"day", "name", "meal_type", "servings", "weight_g", "kcal"})

    day: int | None = Field(default=None, ge=1)
    name: str | None = None
    meal_type: Meal | None = None
    servings: float | None = Field(default=None, gt=0)
    weight_g: float | None = Field(default=None, ge=0)
    kcal: int | None = Field(default=None, ge=0)


class TripFoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day: int
    name: str
    meal_type: Meal
    servings: float
    weight_g: float
    kcal: int
    planner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FoodPlannerUpdate(UpdateSchema):
    non_nullable = frozenset({"target_kcal_per_day", "target_food_g_per_day"})

    target_kcal_per_day: int | None = Field(default=None, ge=0)
    target_food_g_per_day: float | None = Field(default=None, ge=0)


class FoodPlannerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_kcal_per_day: int
    target_food_g_per_day: float
    trip_id: uuid.UUID
    food: list[TripFoodRead]
    created_at: datetime
    updated_at: datetime


def is_checklist_ready(items: Sequence[ChecklistItemRead | SharedChecklistItemRead]) -> bool:
    """True when no checklist item is still to do (done and not-applicable both count)."""
    return all(item.status != ChecklistStatus.TODO for item in items)


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    area: str | None
    trip_type: TripType
    start_date: date | None
    end_date: date | None
    start_trailhead: str | None
    end_trailhead: str | None
    total_distance_m: float | None
    elevation_gain_m: float | None
    water_carry_l: float
    map_link: str | None
    food_plan: FoodPlannerRead | None
    checklist_items: list[ChecklistItemRead]
    created_at: datetime
    updated_at: datetime
    user_id: uuid.UUID
    emergency_contact: str | None
    gear_list: list[TripGearRead]
    notes: list[TripNoteRead]
    share_token: str | None
    share_gear: bool
    share_food: bool
    share_checklist: bool
    share_emergency_contact: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def checklist_ready(self) -> bool:
        return is_checklist_ready(self.checklist_items)


class TripShareRead(BaseModel):
    share_token: str


# Public share-link schemas. Each is its own allowlist rather than an owner schema minus fields, so a field
# added to a model or owner schema stays private until it's added here on purpose. None carry ids or
# timestamps.


class SharedGearItemRead(BaseModel):
    """A closet item as seen through a share link: no private notes or archive state."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    category: GearCategory
    weight_g: float
    kind: GearKind

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category_label(self) -> str:
        # The public page can't call the authenticated /gear/categories to look up labels.
        return self.category.label


class SharedTripGearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gear_item: SharedGearItemRead
    quantity: int
    packed: bool


class SharedChecklistItemRead(BaseModel):
    """Item and status only: details are free text that may hold personal info."""

    model_config = ConfigDict(from_attributes=True)

    item: ChecklistItemKey
    status: ChecklistStatus


class SharedTripFoodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: int
    name: str
    meal_type: Meal
    servings: float
    weight_g: float
    kcal: int


class SharedFoodPlannerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_kcal_per_day: int
    target_food_g_per_day: float
    food: list[SharedTripFoodRead]


class SharedTripOwnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str


class SharedTripRead(BaseModel):
    """Public read-only view of a shared trip; build it with from_trip(), which applies the owner's toggles.

    Core details are always present. Each optional section is always present as a key: null when the owner
    hasn't shared it, and [] when it's shared but empty. Section fields deliberately have no default, so the
    OpenAPI schema marks them required and the UI's generated type keeps the key non-optional.
    """

    name: str
    description: str | None
    area: str | None
    trip_type: TripType
    start_date: date | None
    end_date: date | None
    start_trailhead: str | None
    end_trailhead: str | None
    total_distance_m: float | None
    elevation_gain_m: float | None
    water_carry_l: float
    map_link: str | None
    owner: SharedTripOwnerRead
    gear_list: list[SharedTripGearRead] | None
    food_plan: SharedFoodPlannerRead | None
    checklist_items: list[SharedChecklistItemRead] | None
    emergency_contact: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def checklist_ready(self) -> bool | None:
        """Follows the checklist toggle: null when the checklist isn't shared."""
        return None if self.checklist_items is None else is_checklist_ready(self.checklist_items)

    @classmethod
    def from_trip(cls, trip: Trip) -> SharedTripRead:
        """Build the public view; trip.user must already be loaded (it's raise_on_sql)."""
        return cls(
            name=trip.name,
            description=trip.description,
            area=trip.area,
            trip_type=trip.trip_type,
            start_date=trip.start_date,
            end_date=trip.end_date,
            start_trailhead=trip.start_trailhead,
            end_trailhead=trip.end_trailhead,
            total_distance_m=trip.total_distance_m,
            elevation_gain_m=trip.elevation_gain_m,
            water_carry_l=trip.water_carry_l,
            map_link=trip.map_link,
            owner=SharedTripOwnerRead.model_validate(trip.user),
            gear_list=[SharedTripGearRead.model_validate(line) for line in trip.gear_list]
            if trip.share_gear
            else None,
            food_plan=SharedFoodPlannerRead.model_validate(trip.food_plan)
            if trip.share_food and trip.food_plan is not None
            else None,
            checklist_items=[SharedChecklistItemRead.model_validate(item) for item in trip.checklist_items]
            if trip.share_checklist
            else None,
            emergency_contact=trip.emergency_contact if trip.share_emergency_contact else None,
        )

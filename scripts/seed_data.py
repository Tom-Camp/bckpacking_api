"""Development seed data, transcribed from the maintainer's trip-planner spreadsheets.

Values are kept in the spreadsheets' imperial units (oz, lb, mi, ft) so they can be checked against the
source; seed.py converts them to the canonical metric units the models store. Personal details from the
spreadsheets (emergency contact, private map links) are replaced with placeholders.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.models.gear import GearCategory, GearKind
from app.models.trip import ChecklistItemKey, ChecklistStatus, Meal, TripType
from app.models.user import Unit, UserRole, UserStatus

# TripUpdate ignores unknown keys, so a typo here would silently leave a section unshared; the Literal makes
# mypy catch it.
ShareSection = Literal["share_gear", "share_food", "share_checklist", "share_emergency_contact"]


@dataclass(frozen=True)
class SeedUser:
    email: str
    username: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE
    measurements: Unit = Unit.IMPERIAL
    body_weight_lb: float | None = None


@dataclass(frozen=True)
class SeedGear:
    name: str
    category: GearCategory
    weight_oz: float
    kind: GearKind = GearKind.BASE
    notes: str | None = None


@dataclass(frozen=True)
class SeedFood:
    day: int
    name: str
    meal_type: Meal
    weight_oz: float
    kcal: int


@dataclass(frozen=True)
class SeedTrip:
    name: str
    trip_type: TripType
    start_date: date
    end_date: date
    area: str
    start_trailhead: str
    end_trailhead: str
    distance_mi: float
    elevation_gain_ft: float
    water_carry_l: float
    map_link: str
    emergency_contact: str
    description: str | None = None
    # Closet item name -> quantity. Spreadsheet rows with a quantity of 0 are left out.
    gear: dict[str, int] = field(default_factory=dict)
    gear_packed: bool = False
    checklist: dict[ChecklistItemKey, ChecklistStatus] = field(default_factory=dict)
    food: list[SeedFood] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Sections exposed by a share link; None leaves the trip unshared.
    share_sections: frozenset[ShareSection] | None = None


HIKER = SeedUser(
    email="hiker@example.com",
    username="hiker",
    first_name="Sam",
    last_name="Hiker",
    body_weight_lb=190,
)

USERS = [
    HIKER,
    SeedUser(
        email="admin@example.com", username="admin", first_name="Ada", last_name="Admin", role=UserRole.ADMIN
    ),
    # A second, metric account: checks ownership isolation and metric display.
    SeedUser(
        email="metric@example.com",
        username="metric",
        first_name="Mia",
        last_name="Metric",
        measurements=Unit.METRIC,
        body_weight_lb=140,
    ),
    SeedUser(
        email="blocked@example.com",
        username="blocked",
        first_name="Blake",
        last_name="Blocked",
        status=UserStatus.BLOCKED,
    ),
]

# The "First aid and repair" sheet's "Yes" rows (Shakedown Cruise), kept as notes on the kit items.
_FIRST_AID = (
    "Ibuprofen, acetaminophen, aspirin, Benadryl, cloth tape, roll gauze, assorted bandaids, tweezers, "
    "butterflies, DayQuil, NyQuil, Imodium, Smooth Move tea, Leukotape, Steri-Strips, Neosporin"
)
_REPAIR_KIT = "Aquaseal, Gear Aid patches, repair tape, super glue, sewing needle"
_HYGIENE = "Toothbrush, toothpaste, bidet, trowel, wipes"

# The closet is shared by every trip, so each item has one weight: the Shakedown Cruise figures, which are
# the more recent and complete of the two spreadsheets. "Sleep" items sit under "Shelter" in the sheets.
HIKER_CLOSET = [
    SeedGear("Backpack", GearCategory.SHELTER, 36.2),
    SeedGear("Tent / shelter", GearCategory.SHELTER, 35.1),
    SeedGear("Footprint", GearCategory.SHELTER, 5.2),
    SeedGear("Sleeping bag / quilt", GearCategory.SLEEP, 50.2),
    SeedGear("Sleeping pad", GearCategory.SLEEP, 23.7),
    SeedGear("Pillow", GearCategory.SLEEP, 2.0),
    SeedGear("Rain jacket", GearCategory.CLOTHING, 12.0),
    SeedGear("Rain pants", GearCategory.CLOTHING, 6.0),
    SeedGear("Insulated jacket (puffy)", GearCategory.CLOTHING, 13.3),
    SeedGear("Fleece", GearCategory.CLOTHING, 11.9),
    SeedGear("Extra base layer top", GearCategory.CLOTHING, 15.5),
    SeedGear("Extra socks (pair)", GearCategory.CLOTHING, 1.65),
    SeedGear("Warm hat & gloves", GearCategory.CLOTHING, 4.0),
    SeedGear("Stove", GearCategory.COOKING_WATER, 1.0),
    # No weight in either spreadsheet; left at 0 to show an item still to be weighed.
    SeedGear("Fuel canister", GearCategory.COOKING_WATER, 0, kind=GearKind.CONSUMABLE),
    SeedGear("Cook pot", GearCategory.COOKING_WATER, 4.35),
    SeedGear("Spork/utensil", GearCategory.COOKING_WATER, 0.65),
    SeedGear("Water filter", GearCategory.COOKING_WATER, 6.75),
    SeedGear("Water bottles/reservoir (empty)", GearCategory.COOKING_WATER, 4.9),
    SeedGear("Coffee press", GearCategory.COOKING_WATER, 6.5),
    SeedGear("Mug", GearCategory.COOKING_WATER, 2.2),
    SeedGear("Personal Locator Beacon", GearCategory.NAVIGATION_SAFETY, 3.95),
    SeedGear("Map & compass", GearCategory.NAVIGATION_SAFETY, 3.4),
    SeedGear("Headlamp + batteries", GearCategory.NAVIGATION_SAFETY, 1.55),
    SeedGear("First aid kit", GearCategory.NAVIGATION_SAFETY, 3.7, notes=_FIRST_AID),
    SeedGear("Emergency shelter/bivy", GearCategory.NAVIGATION_SAFETY, 4.0),
    SeedGear("Multi-tool/knife", GearCategory.NAVIGATION_SAFETY, 3.0),
    SeedGear("Lighter/firestarter", GearCategory.NAVIGATION_SAFETY, 1.0),
    SeedGear("Repair kit", GearCategory.NAVIGATION_SAFETY, 1.45, notes=_REPAIR_KIT),
    SeedGear("Toiletries/TP", GearCategory.MISCELLANEOUS, 4.05, notes=_HYGIENE),
    SeedGear("Bear vault", GearCategory.MISCELLANEOUS, 33.0),
    SeedGear("Phone + battery bank", GearCategory.MISCELLANEOUS, 22.35),
    SeedGear("Permit/paper map printout", GearCategory.MISCELLANEOUS, 1.0),
    SeedGear("Chair", GearCategory.MISCELLANEOUS, 20.4),
]

METRIC_CLOSET = [
    SeedGear("Trekking poles", GearCategory.MISCELLANEOUS, 17.6),
    SeedGear("Down quilt", GearCategory.SLEEP, 21.2),
    SeedGear("Trail runners", GearCategory.CLOTHING, 21.0, kind=GearKind.WORN),
]

_EMERGENCY_CONTACT = "Jo Example, 555-0100"

CARVERS_GAP = SeedTrip(
    name="Carver's Gap to 19W",
    trip_type=TripType.POINT_TO_POINT,
    start_date=date(2026, 8, 26),
    end_date=date(2026, 8, 27),
    area="Green Mnt.",
    start_trailhead="Carver's Gap",
    end_trailhead="19W",
    distance_mi=13.2,
    elevation_gain_ft=3195,
    water_carry_l=2,  # the sheet's 4.4 lb of water
    map_link="https://www.gaiagps.com/map/?loc=13.0/-82.1105/36.1063",
    emergency_contact=_EMERGENCY_CONTACT,
    gear={
        "Backpack": 1,
        "Tent / shelter": 1,
        "Sleeping bag / quilt": 1,
        "Sleeping pad": 1,
        "Pillow": 1,
        "Rain jacket": 1,
        "Rain pants": 1,
        "Insulated jacket (puffy)": 1,
        "Extra base layer top": 1,
        "Extra socks (pair)": 2,
        "Warm hat & gloves": 1,
        "Stove": 1,
        "Fuel canister": 1,
        "Cook pot": 1,
        "Spork/utensil": 1,
        "Water filter": 1,
        "Water bottles/reservoir (empty)": 2,
        "Coffee press": 1,
        "Mug": 1,
        "Personal Locator Beacon": 1,
        "Map & compass": 1,
        "Headlamp + batteries": 1,
        "First aid kit": 1,
        "Emergency shelter/bivy": 1,
        "Multi-tool/knife": 1,
        "Lighter/firestarter": 1,
        "Toiletries/TP": 1,
        "Bear vault": 1,
        "Phone + battery bank": 1,
        "Permit/paper map printout": 1,
    },
    gear_packed=True,
    checklist={
        ChecklistItemKey.PERMIT: ChecklistStatus.NOT_APPLICABLE,  # "Permit required? No"
        ChecklistItemKey.WATER_SOURCES: ChecklistStatus.DONE,
        ChecklistItemKey.RESUPPLY_POINTS: ChecklistStatus.NOT_APPLICABLE,
        ChecklistItemKey.SHUTTLE_SCHEDULED: ChecklistStatus.DONE,
        ChecklistItemKey.WEATHER_CHECKED: ChecklistStatus.TODO,
        ChecklistItemKey.CELL_COVERAGE: ChecklistStatus.DONE,
        ChecklistItemKey.OFFLINE_MAP: ChecklistStatus.TODO,
        ChecklistItemKey.FIRE_RESTRICTIONS: ChecklistStatus.TODO,
    },
    # The spreadsheet's menu was never filled in: an empty planner with the default targets.
)

SHAKEDOWN_CRUISE = SeedTrip(
    name="Shakedown Cruise",
    description="Appalachian Trail",
    trip_type=TripType.OUT_AND_BACK,
    start_date=date(2026, 9, 7),
    end_date=date(2026, 9, 8),
    area="Pisgah",
    start_trailhead="19W",
    end_trailhead="19W",
    distance_mi=4.59,
    elevation_gain_ft=1434,
    water_carry_l=2,
    map_link="https://www.gaiagps.com/map/?loc=14.0/-82.42034/36.03276",
    emergency_contact=_EMERGENCY_CONTACT,
    gear={
        "Backpack": 1,
        "Tent / shelter": 1,
        "Footprint": 1,
        "Sleeping bag / quilt": 1,
        "Sleeping pad": 1,
        "Pillow": 1,
        "Rain jacket": 1,
        "Rain pants": 1,
        "Fleece": 1,
        "Extra base layer top": 1,
        "Extra socks (pair)": 2,
        "Stove": 1,
        "Fuel canister": 1,
        "Cook pot": 1,
        "Spork/utensil": 1,
        "Water filter": 1,
        "Water bottles/reservoir (empty)": 2,
        "Coffee press": 1,
        "Mug": 1,
        "Personal Locator Beacon": 1,
        "Map & compass": 1,
        "Headlamp + batteries": 1,
        "First aid kit": 1,
        "Multi-tool/knife": 1,
        "Lighter/firestarter": 2,
        "Repair kit": 1,
        "Toiletries/TP": 1,
        "Bear vault": 1,
        "Phone + battery bank": 1,
        "Chair": 1,
    },
    checklist={
        ChecklistItemKey.PERMIT: ChecklistStatus.NOT_APPLICABLE,
        ChecklistItemKey.WATER_SOURCES: ChecklistStatus.DONE,
        ChecklistItemKey.RESUPPLY_POINTS: ChecklistStatus.NOT_APPLICABLE,
        ChecklistItemKey.SHUTTLE_SCHEDULED: ChecklistStatus.NOT_APPLICABLE,
        ChecklistItemKey.WEATHER_CHECKED: ChecklistStatus.TODO,
        ChecklistItemKey.CELL_COVERAGE: ChecklistStatus.DONE,
        ChecklistItemKey.OFFLINE_MAP: ChecklistStatus.TODO,
        ChecklistItemKey.FIRE_RESTRICTIONS: ChecklistStatus.TODO,
        ChecklistItemKey.ROUTE_SHARED: ChecklistStatus.TODO,
    },
    food=[
        SeedFood(1, "Trail mix", Meal.SNACK, 2.0, 350),
        SeedFood(1, "Thai Curry", Meal.DINNER, 3.85, 380),
        SeedFood(2, "Granola with Blueberries, Almonds & Milk", Meal.BREAKFAST, 5.35, 620),
        SeedFood(2, "Peanut Apricot", Meal.LUNCH, 5.5, 665),
        SeedFood(2, "Trail mix", Meal.SNACK, 2.0, 350),
    ],
    notes=[
        "Start trailhead: 36.03276, -82.42034",
        # The sheet's "OT" rows: food carried beyond the two-day menu.
        "Spare food: Granola with Blueberries, Almonds & Milk (5.35 oz, 620 kcal); Cranberry Almond "
        "(5.8 oz, 650 kcal); Santa Fe Style Rice & Beans with Chicken (5.7 oz, 590 kcal).",
    ],
    share_sections=frozenset({"share_gear", "share_food", "share_checklist"}),
)

HIKER_TRIPS = [CARVERS_GAP, SHAKEDOWN_CRUISE]

import pytest
from sqlmodel import SQLModel

from app.models import FoodPlanner, Gear, Trip, TripChecklistItem, TripFood, TripNote, User
from app.schemas.base import UpdateSchema
from app.schemas.trip import (
    ChecklistItemUpdate,
    FoodPlannerUpdate,
    GearUpdate,
    TripFoodUpdate,
    TripNoteUpdate,
    TripUpdate,
)
from app.schemas.user import UserUpdate

UPDATE_SCHEMAS: list[tuple[type[UpdateSchema], type[SQLModel]]] = [
    (TripUpdate, Trip),
    (GearUpdate, Gear),
    (TripNoteUpdate, TripNote),
    (ChecklistItemUpdate, TripChecklistItem),
    (FoodPlannerUpdate, FoodPlanner),
    (TripFoodUpdate, TripFood),
    (UserUpdate, User),
]

# Schema fields with no backing column. `picture` is tracked in API_GAPS.md 1.5.
_NOT_COLUMNS = {(UserUpdate, "picture")}


@pytest.mark.parametrize(("schema", "model"), UPDATE_SCHEMAS, ids=lambda x: x.__name__)
def test_non_nullable_matches_model_columns(schema: type[UpdateSchema], model: type[SQLModel]) -> None:
    # Keeps the schemas in step with the models: a NOT NULL column must reject an explicit null
    # (otherwise PATCH writes None and fails with an IntegrityError / 500), and a nullable column
    # must accept one (otherwise the client can't clear it).
    columns = model.__table__.c  # type: ignore[attr-defined]
    for field in schema.model_fields:
        if (schema, field) in _NOT_COLUMNS:
            continue
        assert (field in schema.non_nullable) == (not columns[field].nullable), field


def test_non_nullable_fields_are_not_nullable_in_json_schema() -> None:
    properties = TripUpdate.model_json_schema()["properties"]

    assert properties["name"] == {"type": "string", "title": "Name"}
    assert properties["measurements"] == {"$ref": "#/$defs/Unit"}
    assert {"type": "null"} in properties["end_trailhead"]["anyOf"]


def test_non_nullable_rejects_unknown_field_names() -> None:
    with pytest.raises(TypeError, match="unknown fields"):

        class _Typo(UpdateSchema):
            non_nullable = frozenset({"nmae"})
            name: str | None = None

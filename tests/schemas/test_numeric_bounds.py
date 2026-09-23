import types
from typing import Union, get_args, get_origin

import annotated_types
import pytest
from pydantic import BaseModel

from app.schemas import trip as trip_schemas
from app.schemas import user as user_schemas

REQUEST_SCHEMAS = [
    obj
    for module in (trip_schemas, user_schemas)
    for name, obj in vars(module).items()
    if isinstance(obj, type)
    and issubclass(obj, BaseModel)
    and obj.__module__ == module.__name__
    and name.endswith(("Create", "Update"))
]


def _is_numeric(annotation: object) -> bool:
    if get_origin(annotation) in (Union, types.UnionType):
        return any(_is_numeric(arg) for arg in get_args(annotation))
    return annotation in (int, float)


def test_request_schemas_found() -> None:
    assert {s.__name__ for s in REQUEST_SCHEMAS} >= {"TripCreate", "GearUpdate", "UserUpdate"}


@pytest.mark.parametrize("schema", REQUEST_SCHEMAS, ids=lambda s: s.__name__)
def test_numeric_request_fields_have_a_lower_bound(schema: type[BaseModel]) -> None:
    # Weights, quantities, calories, distances and targets can't be negative; any new numeric
    # request field has to declare Field(ge=...) or Field(gt=...).
    for name, field in schema.model_fields.items():
        if _is_numeric(field.annotation):
            bounds = [m for m in field.metadata if isinstance(m, annotated_types.Ge | annotated_types.Gt)]
            assert bounds, f"{schema.__name__}.{name} has no lower bound"

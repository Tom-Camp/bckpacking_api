from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


def _drop_null_from_non_nullable(schema: dict[str, Any], model_cls: type[BaseModel]) -> None:
    # Fields are declared `X | None = None` so they can be omitted, which makes the generated
    # schema say `anyOf: [X, null]`. For non-nullable fields, advertise just `X` so the
    # frontend's generated client doesn't offer `null` as a valid value.
    properties = schema.get("properties", {})
    for name in getattr(model_cls, "non_nullable", ()):
        prop = properties[name]
        variants = [v for v in prop.pop("anyOf", []) if v != {"type": "null"}]
        if len(variants) == 1:
            prop.update(variants[0])
        elif variants:
            prop["anyOf"] = variants
        prop.pop("default", None)


class UpdateSchema(BaseModel):
    """Base for PATCH request bodies.

    Every field defaults to None so it can be omitted; services apply only the fields the client
    actually sent (``model_dump(exclude_unset=True)``), so an explicit ``null`` clears a nullable
    field. Fields listed in ``non_nullable`` (NOT NULL columns) reject an explicit ``null`` with a 422.
    """

    model_config = ConfigDict(json_schema_extra=_drop_null_from_non_nullable)

    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        unknown = cls.non_nullable - cls.model_fields.keys()
        if unknown:
            raise TypeError(f"{cls.__name__}.non_nullable names unknown fields: {sorted(unknown)}")

    @field_validator("*")
    @classmethod
    def _reject_null(cls, v: object, info: ValidationInfo) -> object:
        if v is None and info.field_name in cls.non_nullable:
            raise ValueError("field cannot be null")
        return v

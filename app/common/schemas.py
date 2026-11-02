from decimal import Decimal
from typing import Annotated, Any, ClassVar

from fastapi import Depends, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


# Money and percentages always travel as strings with 2 decimals, e.g. "1500.00".
Money = Annotated[
    Decimal, Field(ge=0, max_digits=12, decimal_places=2), AfterValidator(_two_places)
]
Percent = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2), AfterValidator(_two_places)]


class Schema(BaseModel):
    """Base for request and response DTOs. Responses can be built straight from ORM objects."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class UpdateSchema(Schema):
    """PATCH body: only the fields that were sent change.

    Fields named in `not_null` may be left out but can't be sent as null.
    """

    not_null: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _reject_nulls(self):
        for name in self.not_null:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} can't be empty")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class Ref(Schema):
    """Small {id, name} reference to a related record."""

    id: int
    name: str


class Page[T](Schema):
    items: list[T]
    total: int
    page: int
    size: int


class PageParams(Schema):
    page: int = 1
    size: int = 20


def _page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


PageQuery = Annotated[PageParams, Depends(_page_params)]

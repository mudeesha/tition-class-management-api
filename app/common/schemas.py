import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from fastapi import Depends, Query
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    model_validator,
)


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


# Money and percentages always travel as strings with 2 decimals, e.g. "1500.00".
Money = Annotated[
    Decimal, Field(ge=0, max_digits=12, decimal_places=2), AfterValidator(_two_places)
]
Percent = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2), AfterValidator(_two_places)]
# Like Money, but may be negative (e.g. a balance after paying a teacher ahead).
SignedMoney = Annotated[
    Decimal, Field(max_digits=12, decimal_places=2), AfterValidator(_two_places)
]


def _parse_month(value: Any) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    if isinstance(value, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        return date(int(value[:4]), int(value[5:]), 1)
    raise ValueError("Use the format YYYY-MM, e.g. 2026-12")


# A calendar month, e.g. "2026-12". Stored as the first day of the month.
Month = Annotated[
    date,
    BeforeValidator(_parse_month),
    PlainSerializer(lambda d: d.strftime("%Y-%m"), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": r"^\d{4}-\d{2}$", "examples": ["2026-12"]}),
]


def month_of(day: date) -> date:
    return day.replace(day=1)


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


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

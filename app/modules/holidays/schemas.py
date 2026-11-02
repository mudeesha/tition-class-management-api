import datetime as dt

from pydantic import Field

from app.common.schemas import Schema, UpdateSchema
from app.modules.branches.schemas import BranchRef


class HolidayCreate(Schema):
    date: dt.date
    name: str = Field(min_length=1, max_length=150)
    branch_id: int | None = Field(None, description="Leave empty for all branches")


class HolidayUpdate(UpdateSchema):
    not_null = ("date", "name")

    date: dt.date | None = None
    name: str | None = Field(None, min_length=1, max_length=150)
    branch_id: int | None = None


class HolidayOut(Schema):
    id: int
    date: dt.date
    name: str
    branch: BranchRef | None  # None = all branches

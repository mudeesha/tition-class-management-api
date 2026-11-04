import datetime as dt
from typing import Literal

from pydantic import Field, model_validator

from app.common.schemas import Money, Month, Schema, UpdateSchema
from app.modules.classes.schemas import ClassRef, TeacherRef
from app.modules.students.schemas import StudentRef
from app.modules.tutes.models import TuteAccess

# Why a student can't have a tute.
NoAccess = Literal["not_in_class", "class_fee_unpaid", "tute_unpaid"]


class TuteCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    number: int | None = Field(None, ge=1, le=9999)
    month: Month
    class_ids: list[int] = Field(min_length=1)
    teacher_id: int | None = Field(None, description="Leave out to use the first class's teacher")
    access_type: TuteAccess = TuteAccess.FREE
    price: Money | None = Field(None, description="Needed for paid tutes")
    has_hard_copy: bool = True

    @model_validator(mode="after")
    def _price(self):
        if self.access_type == TuteAccess.PAID and not self.price:
            raise ValueError("Paid tutes need a price")
        if self.access_type == TuteAccess.FREE:
            self.price = None
        return self


class TuteUpdate(UpdateSchema):
    not_null = ("title", "month", "class_ids", "teacher_id", "access_type", "has_hard_copy")

    title: str | None = Field(None, min_length=1, max_length=200)
    number: int | None = Field(None, ge=1, le=9999)
    month: Month | None = None
    class_ids: list[int] | None = Field(None, min_length=1)
    teacher_id: int | None = None
    access_type: TuteAccess | None = None
    price: Money | None = None
    has_hard_copy: bool | None = None


class TuteRef(Schema):
    id: int
    title: str
    month: Month


class TuteOut(Schema):
    id: int
    title: str
    number: int | None
    month: Month
    teacher: TeacherRef
    classes: list[ClassRef]
    access_type: TuteAccess
    price: Money | None
    has_hard_copy: bool
    has_file: bool
    file_name: str | None
    file_size: int | None


class TuteStudentOut(Schema):
    """One student of the tute's classes: can they have it, and did they get the hard copy."""

    student: StudentRef
    allowed: bool
    reason: NoAccess | None
    issued_at: dt.datetime | None


class IssueIn(Schema):
    student_id: int

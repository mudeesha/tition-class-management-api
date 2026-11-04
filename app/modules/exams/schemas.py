import datetime as dt
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from app.common.schemas import Schema, UpdateSchema
from app.modules.classes.schemas import ClassRef, SubjectRef, TeacherRef
from app.modules.students.schemas import StudentRef


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


# Marks like "45.50". Halves are common.
Marks = Annotated[Decimal, Field(ge=0, le=9999, decimal_places=2), AfterValidator(_two_places)]


class PartIn(Schema):
    id: int | None = Field(None, description="Leave out for a new part")
    name: str = Field(min_length=1, max_length=50)
    max_marks: Marks = Field(gt=0)


class ExamCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    date: dt.date
    class_ids: list[int] = Field(min_length=1)
    subject_id: int | None = Field(None, description="Leave out to use the first class's subject")
    teacher_id: int | None = Field(None, description="Leave out to use the first class's teacher")
    parts: list[PartIn] = Field(min_length=1, description="e.g. MCQ 40, Structured 30, Essay 30")


class ExamUpdate(UpdateSchema):
    """`parts` replaces the list: keep ids to keep parts, leave one out to delete it."""

    not_null = ("title", "date", "class_ids", "parts", "published")

    title: str | None = Field(None, min_length=1, max_length=200)
    date: dt.date | None = None
    class_ids: list[int] | None = Field(None, min_length=1)
    parts: list[PartIn] | None = Field(None, min_length=1)
    published: bool | None = None


class PartOut(Schema):
    id: int
    name: str
    max_marks: Marks


class ExamOut(Schema):
    id: int
    title: str
    date: dt.date
    subject: SubjectRef
    teacher: TeacherRef
    classes: list[ClassRef]
    parts: list[PartOut]
    max_total: Marks
    published: bool


class MarkOut(Schema):
    part_id: int
    marks: Marks | None
    is_absent: bool


class SheetRow(Schema):
    """A student who sits the exam, with the marks entered so far."""

    student: StudentRef
    class_id: int
    marks: list[MarkOut]


class MarkIn(Schema):
    student_id: int
    part_id: int
    marks: Marks | None = None
    is_absent: bool = False

    @model_validator(mode="after")
    def _one(self):
        if self.is_absent:
            self.marks = None
        return self


class MarksIn(Schema):
    marks: list[MarkIn] = Field(min_length=1)


class ResultRow(Schema):
    student: StudentRef
    class_id: int
    total: Marks | None = Field(description="Empty when absent for the whole paper")
    percent: Decimal | None
    absent: bool
    rank: int | None = Field(description="Among everyone who sat (1 = top)")
    class_rank: int | None = Field(description="Within the student's class")
    parts: list[MarkOut]


class ResultsOut(Schema):
    exam: ExamOut
    sat: int
    absent: int
    average: Decimal | None
    highest: Decimal | None
    rows: list[ResultRow] = Field(description="Best first; absent students last")

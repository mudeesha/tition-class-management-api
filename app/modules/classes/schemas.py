from datetime import time

from pydantic import Field, ValidationInfo, field_validator

from app.common.schemas import Money, Schema, UpdateSchema
from app.modules.branches.schemas import BranchRef
from app.modules.classes.models import ClassLevel, ClassType
from app.modules.subjects.models import SubjectLevel


class ClassCreate(Schema):
    branch_id: int
    subject_id: int
    teacher_id: int
    level: ClassLevel
    exam_year: int | None = Field(
        None, ge=2000, le=2100, validate_default=True, description="Required for A/L"
    )
    name: str = Field("Class 1", min_length=1, max_length=100)
    class_type: ClassType = ClassType.COMMON
    monthly_fee: Money
    hall_id: int | None = Field(None, description="Default hall for the class's schedules")

    @field_validator("exam_year")
    @classmethod
    def _al_needs_year(cls, v: int | None, info: ValidationInfo) -> int | None:
        if v is None and info.data.get("level") == ClassLevel.AL:
            raise ValueError("A/L classes need an exam year")
        return v


class ClassUpdate(UpdateSchema):
    """The branch can't change: the class's receipts and attendance belong to it."""

    not_null = (
        "subject_id",
        "teacher_id",
        "level",
        "name",
        "class_type",
        "monthly_fee",
        "is_active",
    )

    subject_id: int | None = None
    teacher_id: int | None = None
    level: ClassLevel | None = None
    exam_year: int | None = Field(None, ge=2000, le=2100)
    name: str | None = Field(None, min_length=1, max_length=100)
    class_type: ClassType | None = None
    monthly_fee: Money | None = None
    hall_id: int | None = None
    is_active: bool | None = None


class ScheduleCreate(Schema):
    weekday: int = Field(ge=1, le=7, description="1 = Monday ... 7 = Sunday")
    start_time: time
    end_time: time
    hall_id: int | None = Field(None, description="Leave out to use the class's hall")

    @field_validator("end_time")
    @classmethod
    def _after_start(cls, v: time, info: ValidationInfo) -> time:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("Must be after the start time")
        return v


class ScheduleUpdate(UpdateSchema):
    not_null = ("weekday", "start_time", "end_time")

    weekday: int | None = Field(None, ge=1, le=7)
    start_time: time | None = None
    end_time: time | None = None
    hall_id: int | None = None


class TeacherRef(Schema):
    id: int
    name: str


class SubjectRef(Schema):
    id: int
    name: str
    level: SubjectLevel | None


class HallRef(Schema):
    id: int
    name: str


class ScheduleOut(Schema):
    id: int
    weekday: int
    start_time: time
    end_time: time
    hall: HallRef | None


class ClassRef(Schema):
    id: int
    title: str
    branch_id: int
    teacher: TeacherRef
    monthly_fee: Money


class ClassOut(Schema):
    id: int
    title: str
    branch: BranchRef
    subject: SubjectRef
    teacher: TeacherRef
    level: ClassLevel
    exam_year: int | None
    name: str
    class_type: ClassType
    monthly_fee: Money
    hall: HallRef | None
    is_active: bool
    schedules: list[ScheduleOut]
    student_count: int = Field(0, description="Students in the class now")


class TimetableEntryOut(ScheduleOut):
    tuition_class: ClassRef

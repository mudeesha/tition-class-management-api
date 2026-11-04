import datetime as dt

from pydantic import Field

from app.common.schemas import Month, Schema, UpdateSchema
from app.modules.branches.schemas import BranchRef
from app.modules.classes.schemas import ClassRef
from app.modules.students.models import CardType, EnrollmentStatus


class StudentCreate(Schema):
    name: str = Field(min_length=1, max_length=150)
    school: str | None = Field(None, max_length=150)
    grade: int | None = Field(None, ge=1, le=13, description="School grade, 1–13")
    exam_year: int | None = Field(None, ge=2000, le=2100, description="O/L or A/L year")
    phone: str | None = Field(None, max_length=30)
    guardian_name: str | None = Field(None, max_length=150)
    guardian_phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    home_branch_id: int
    admitted_on: dt.date | None = Field(None, description="Defaults to today")


class StudentUpdate(UpdateSchema):
    not_null = ("name", "home_branch_id", "admitted_on", "is_active")

    name: str | None = Field(None, min_length=1, max_length=150)
    school: str | None = Field(None, max_length=150)
    grade: int | None = Field(None, ge=1, le=13)
    exam_year: int | None = Field(None, ge=2000, le=2100)
    phone: str | None = Field(None, max_length=30)
    guardian_name: str | None = Field(None, max_length=150)
    guardian_phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    home_branch_id: int | None = None
    admitted_on: dt.date | None = None
    is_active: bool | None = None


class PortalAccountIn(Schema):
    password: str = Field(min_length=8, max_length=128, description="First password to give them")


class PortalAccountOut(Schema):
    """The student's login for the student portal."""

    username: str | None = Field(description="Empty until an account is made")
    active: bool


class StudentRef(Schema):
    id: int
    code: str
    name: str


class StudentOut(Schema):
    id: int
    code: str
    qr_token: str
    name: str
    school: str | None
    grade: int | None
    exam_year: int | None
    phone: str | None
    guardian_name: str | None
    guardian_phone: str | None
    address: str | None
    home_branch: BranchRef
    admitted_on: dt.date
    is_active: bool


class EnrollmentCreate(Schema):
    student_id: int
    class_id: int
    joined_on: dt.date | None = Field(None, description="Defaults to today")
    card_type: CardType = CardType.FULL


class EnrollmentUpdate(UpdateSchema):
    not_null = ("card_type",)

    card_type: CardType | None = None


class LeaveIn(Schema):
    end_month: Month = Field(description="The last month the student attends and pays for")


class PromoteIn(Schema):
    from_class_id: int
    to_class_id: int
    start_month: Month = Field(description="First month in the new class")
    enrollment_ids: list[int] | None = Field(
        None, description="Who to move. Leave out to move everyone in the class."
    )
    close_old_class: bool = Field(
        False, description="Make the old class inactive once nobody is left in it"
    )


class EnrollmentOut(Schema):
    id: int
    student: StudentRef
    tuition_class: ClassRef
    joined_on: dt.date
    start_month: Month
    end_month: Month | None
    card_type: CardType
    status: EnrollmentStatus
    promoted_to_id: int | None


class StudentProfileOut(StudentOut):
    """The student with their classes, current ones first. Only branches you can see."""

    enrollments: list[EnrollmentOut]


class SkippedOut(Schema):
    enrollment_id: int
    student: StudentRef
    reason: str


class PromoteOut(Schema):
    promoted: int
    skipped: list[SkippedOut]

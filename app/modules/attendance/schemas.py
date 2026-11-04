import datetime as dt
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.common.schemas import Money, Schema, UpdateSchema
from app.modules.attendance.models import (
    AttendanceMethod,
    AttendanceStatus,
    FeeStatus,
    SessionKind,
    SessionStatus,
)
from app.modules.classes.schemas import ClassRef, HallRef
from app.modules.students.models import CardType
from app.modules.students.schemas import StudentRef


class SessionCounts(Schema):
    present: int = 0
    late: int = 0
    absent: int = 0


class SessionOut(Schema):
    id: int
    tuition_class: ClassRef
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    hall: HallRef | None
    kind: SessionKind
    status: SessionStatus
    note: str | None
    counts: SessionCounts = SessionCounts()


class ExtraSessionIn(Schema):
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    hall_id: int | None = Field(None, description="Leave out to use the class's hall")
    note: str | None = Field(None, max_length=255)

    @field_validator("end_time")
    @classmethod
    def _after_start(cls, v: dt.time, info: ValidationInfo) -> dt.time:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("Must be after the start time")
        return v


class SessionUpdate(UpdateSchema):
    """Cancel or restore a day, or move it for that day only."""

    not_null = ("status", "start_time", "end_time")

    status: SessionStatus | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    hall_id: int | None = None
    note: str | None = Field(None, max_length=255)


class AttendanceMark(Schema):
    status: AttendanceStatus
    method: AttendanceMethod
    fee_status: FeeStatus | None
    marked_at: dt.datetime


class RosterRow(Schema):
    """A student of the class on that day: their fee status and attendance, if marked."""

    student: StudentRef
    enrollment_id: int
    card_type: CardType
    fee_status: FeeStatus
    attendance: AttendanceMark | None


class MarkIn(Schema):
    student_id: int
    status: AttendanceStatus


class MarkAllIn(Schema):
    marks: list[MarkIn] = Field(min_length=1)


class ScanIn(Schema):
    """From the QR card, or the student code typed in when a card is missing."""

    branch_id: int = Field(description="The branch where the scanner is")
    qr_token: str | None = Field(None, max_length=64)
    student_code: str | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def _one_of(self):
        if not self.qr_token and not self.student_code:
            raise ValueError("Give a qr_token or a student_code")
        return self


class SessionRef(Schema):
    id: int
    tuition_class: ClassRef
    date: dt.date
    start_time: dt.time
    end_time: dt.time


class ScanOut(Schema):
    """`in`: marked present or late (fee paid, or a warning). `blocked`: fee unpaid after the
    warning days, nothing is marked. `already`: scanned before. `no_class`: nothing now."""

    outcome: Literal["in", "already", "blocked", "no_class"]
    message: str
    student: StudentRef
    session: SessionRef | None = None
    fee_status: FeeStatus | None = None
    attendance_status: AttendanceStatus | None = None
    amount_due: Money | None = Field(None, description="This month's fee, when unpaid")


class AttendanceOut(Schema):
    id: int
    session: SessionRef
    status: AttendanceStatus
    method: AttendanceMethod
    fee_status: FeeStatus | None
    marked_at: dt.datetime

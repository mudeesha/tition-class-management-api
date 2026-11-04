import datetime as dt
from decimal import Decimal

from pydantic import Field

from app.common.schemas import Money, Month, Schema
from app.modules.attendance.schemas import SessionOut
from app.modules.classes.schemas import ClassRef


class Unpaid(Schema):
    students: int
    amount: Money


class TodayAttendance(Schema):
    came: int
    absent: int


class DashboardOut(Schema):
    """Each part is empty (null) when the viewer lacks the permission for it."""

    date: dt.date
    classes_today: list[SessionOut] | None = None
    attendance_today: TodayAttendance | None = None
    collected_today: Money | None = None
    receipts_today: int | None = None
    collected_this_month: Money | None = None
    cash_not_handed_over: Money | None = None
    unpaid_this_month: Unpaid | None = Field(
        None, description="This month's class fees not paid yet"
    )
    active_students: int | None = None


class StudentContact(Schema):
    id: int
    code: str
    name: str
    phone: str | None
    guardian_phone: str | None


class DueRow(Schema):
    student: StudentContact
    tuition_class: ClassRef
    months: list[Month]
    amount: Money


class DuesReport(Schema):
    until: Month
    rows: list[DueRow] = Field(description="Most owed first")
    total: Money


class CollectionDay(Schema):
    date: dt.date
    receipts: int
    total: Money
    cash: Money
    card: Money
    bank_transfer: Money


class CollectionsReport(Schema):
    days: list[CollectionDay]
    class_fees: Money
    admission: Money
    tutes: Money
    total: Money


class ClassAttendance(Schema):
    tuition_class: ClassRef
    days: int = Field(description="Class days held (not cancelled) so far that month")
    students: int
    came: int
    absent: int
    rate: Decimal | None = Field(description="Came as a % of students × days")


class AttendanceReport(Schema):
    month: Month
    rows: list[ClassAttendance]

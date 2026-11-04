import datetime as dt
from decimal import Decimal

from app.common.schemas import Money, Month, Schema
from app.modules.exams.schemas import Marks
from app.modules.tutes.models import TuteAccess
from app.modules.tutes.schemas import NoAccess


class PortalTuteOut(Schema):
    id: int
    title: str
    number: int | None
    month: Month
    access_type: TuteAccess
    price: Money | None
    teacher_name: str
    has_file: bool
    allowed: bool
    reason: NoAccess | None
    hard_copy_given: bool


class PortalPartOut(Schema):
    name: str
    max_marks: Marks
    marks: Marks | None
    is_absent: bool


class PortalExamOut(Schema):
    id: int
    title: str
    date: dt.date
    subject: str
    max_total: Marks
    total: Marks | None
    percent: Decimal | None
    absent: bool
    rank: int | None
    class_rank: int | None
    sat: int
    parts: list[PortalPartOut]

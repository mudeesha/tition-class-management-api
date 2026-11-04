from __future__ import annotations

import datetime as dt
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.branches.models import Hall
from app.modules.classes.models import TuitionClass
from app.modules.students.models import Student


class SessionKind(StrEnum):
    REGULAR = "regular"  # from the weekly timetable
    EXTRA = "extra"  # added for one day


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class ClassSession(IdMixin, TenantMixin, TimestampMixin, Base):
    """One day a class meets. Regular days are made from the weekly times when first needed,
    skipping holidays; extra days are added by hand."""

    __tablename__ = "class_sessions"
    __table_args__ = (
        Index(
            "uq_class_sessions_schedule_date",
            "schedule_id",
            "date",
            unique=True,
            postgresql_where=text("schedule_id IS NOT NULL"),
        ),
        CheckConstraint("start_time < end_time", name="starts_before_end"),
    )

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    # The weekly time it came from. Changing that time redoes the future days.
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_schedules.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    start_time: Mapped[dt.time] = mapped_column(Time)
    end_time: Mapped[dt.time] = mapped_column(Time)
    hall_id: Mapped[int | None] = mapped_column(ForeignKey("halls.id"))
    kind: Mapped[SessionKind] = mapped_column(str_enum(SessionKind), default=SessionKind.REGULAR)
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus), default=SessionStatus.SCHEDULED
    )
    note: Mapped[str | None] = mapped_column(String(255))

    tuition_class: Mapped[TuitionClass] = relationship(lazy="joined")
    hall: Mapped[Hall | None] = relationship(lazy="joined")


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"


class AttendanceMethod(StrEnum):
    QR = "qr"
    MANUAL = "manual"


class FeeStatus(StrEnum):
    """This month's fee for the class, when the student came in."""

    PAID = "paid"
    WARNING = "warning"  # unpaid, still within the warning days
    BLOCKED = "blocked"  # unpaid after the warning days: entry refused


class Attendance(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "attendances"
    __table_args__ = (UniqueConstraint("session_id", "student_id"),)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"), index=True)
    status: Mapped[AttendanceStatus] = mapped_column(str_enum(AttendanceStatus))
    method: Mapped[AttendanceMethod] = mapped_column(str_enum(AttendanceMethod))
    fee_status: Mapped[FeeStatus | None] = mapped_column(str_enum(FeeStatus))
    marked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    marked_at: Mapped[dt.datetime]

    session: Mapped[ClassSession] = relationship(lazy="joined")
    student: Mapped[Student] = relationship(lazy="joined")

from __future__ import annotations

from datetime import date
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.branches.models import Branch
from app.modules.classes.models import TuitionClass
from app.modules.users.models import User


class Student(IdMixin, TenantMixin, TimestampMixin, Base):
    """A student of the institute. They can join classes in any of its branches."""

    __tablename__ = "students"
    __table_args__ = (CheckConstraint("grade BETWEEN 1 AND 13", name="grade_range"),)

    # e.g. SAYA-00042. Unique across all institutes, because it becomes the student's
    # username when the student portal arrives.
    code: Mapped[str] = mapped_column(String(50), unique=True)
    # What the QR card holds. Random, so cards can't be guessed; a new one voids the old card.
    qr_token: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    school: Mapped[str | None] = mapped_column(String(150))
    grade: Mapped[int | None] = mapped_column(SmallInteger)  # school grade, 1–13
    exam_year: Mapped[int | None] = mapped_column(Integer)  # O/L or A/L year
    phone: Mapped[str | None] = mapped_column(String(30))
    guardian_name: Mapped[str | None] = mapped_column(String(150))
    guardian_phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))
    home_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    # Their portal login (username = student code), once staff create it.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    admitted_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    home_branch: Mapped[Branch] = relationship(lazy="joined")
    user: Mapped[User | None] = relationship()


class CardType(StrEnum):
    FULL = "full"
    HALF = "half"  # pays 50% every month
    FREE = "free"  # pays nothing


class EnrollmentStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"
    PROMOTED = "promoted"  # moved on to the next class; see promoted_to_id


class Enrollment(IdMixin, TenantMixin, TimestampMixin, Base):
    """A student in a class from start_month to end_month.

    Leaving and re-joining makes a new row, and promotion links the old row to the new one,
    so the full history stays.
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        Index(
            "uq_enrollments_one_active",
            "student_id",
            "class_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint("end_month IS NULL OR end_month >= start_month", name="months_in_order"),
    )

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    # The class's branch, copied here so branch access works like for other branch tables.
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    # The day they started. The late-join rule (phase 3) compares its day of month.
    joined_on: Mapped[date] = mapped_column(Date)
    # First month they pay for, and the last one (set when they leave or are promoted).
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    card_type: Mapped[CardType] = mapped_column(str_enum(CardType), default=CardType.FULL)
    status: Mapped[EnrollmentStatus] = mapped_column(
        str_enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE
    )
    promoted_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("enrollments.id", ondelete="SET NULL")
    )

    student: Mapped[Student] = relationship(lazy="joined")
    tuition_class: Mapped[TuitionClass] = relationship(lazy="joined")

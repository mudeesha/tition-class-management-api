from __future__ import annotations

from datetime import time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger, String, Time, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.branches.models import Branch, Hall
from app.modules.subjects.models import Subject
from app.modules.teachers.models import Teacher

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ClassLevel(StrEnum):
    """Grade classes run per school grade; O/L and A/L classes run per exam year."""

    GRADE_1 = "grade_1"
    GRADE_2 = "grade_2"
    GRADE_3 = "grade_3"
    GRADE_4 = "grade_4"
    GRADE_5 = "grade_5"
    GRADE_6 = "grade_6"
    GRADE_7 = "grade_7"
    GRADE_8 = "grade_8"
    GRADE_9 = "grade_9"
    GRADE_10 = "grade_10"
    GRADE_11 = "grade_11"
    OL = "ol"
    AL = "al"

    @property
    def grade(self) -> int | None:
        return int(self.value[6:]) if self.value.startswith("grade_") else None

    @property
    def label(self) -> str:
        if self.grade is not None:
            return f"Grade {self.grade}"
        return "O/L" if self is ClassLevel.OL else "A/L"


class ClassType(StrEnum):
    COMMON = "common"  # a group class, usually in a hall
    INDIVIDUAL = "individual"  # one student or a small group


class TuitionClass(IdMixin, TenantMixin, TimestampMixin, Base):
    """One class: a teacher teaching a subject to one level (or exam year) at one branch."""

    __tablename__ = "classes"
    __table_args__ = (
        CheckConstraint("level <> 'al' OR exam_year IS NOT NULL", name="al_needs_exam_year"),
        CheckConstraint("monthly_fee >= 0", name="fee_not_negative"),
    )

    # A class stays in its branch: receipts, halls and attendance all belong to it.
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    level: Mapped[ClassLevel] = mapped_column(str_enum(ClassLevel))
    exam_year: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))  # "Class 1", "Revision", ...
    class_type: Mapped[ClassType] = mapped_column(str_enum(ClassType), default=ClassType.COMMON)
    monthly_fee: Mapped[Decimal]
    # Default hall for new schedules.
    hall_id: Mapped[int | None] = mapped_column(ForeignKey("halls.id"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    branch: Mapped[Branch] = relationship(lazy="joined")
    subject: Mapped[Subject] = relationship(lazy="joined")
    teacher: Mapped[Teacher] = relationship(lazy="joined")
    hall: Mapped[Hall | None] = relationship(lazy="joined")
    schedules: Mapped[list[ClassSchedule]] = relationship(
        back_populates="tuition_class",
        lazy="selectin",
        order_by="(ClassSchedule.weekday, ClassSchedule.start_time)",
        cascade="all, delete-orphan",
    )

    @property
    def title(self) -> str:
        """e.g. "Grade 6 Mathematics – Class 1" or "2027 A/L Physics – Class 1"."""
        level = self.level.label
        if self.exam_year is not None:
            level = f"{self.exam_year} {level}"
        return f"{level} {self.subject.name} – {self.name}"


class ClassSchedule(IdMixin, TenantMixin, TimestampMixin, Base):
    """A weekly slot, e.g. Saturday 08:00–10:00 in Hall A."""

    __tablename__ = "class_schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday_range"),
        CheckConstraint("start_time < end_time", name="starts_before_end"),
    )

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 1 = Monday ... 7 = Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    hall_id: Mapped[int | None] = mapped_column(ForeignKey("halls.id"), index=True)

    tuition_class: Mapped[TuitionClass] = relationship(back_populates="schedules")
    hall: Mapped[Hall | None] = relationship(lazy="joined")

    @property
    def when(self) -> str:
        return f"{WEEKDAYS[self.weekday - 1]} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin
from app.modules.classes.models import TuitionClass
from app.modules.subjects.models import Subject
from app.modules.teachers.models import Teacher

exam_classes = Table(
    "exam_classes",
    Base.metadata,
    Column("exam_id", ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
)


class Exam(IdMixin, TenantMixin, TimestampMixin, Base):
    """A paper for one or more classes (e.g. Class 1 and Class 2 together).

    Totals and ranks are worked out from the marks, never stored.
    """

    __tablename__ = "exams"

    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    # Students see their marks in the portal only once published.
    published: Mapped[bool] = mapped_column(default=False, server_default=false())

    subject: Mapped[Subject] = relationship(lazy="joined")
    teacher: Mapped[Teacher] = relationship(lazy="joined")
    classes: Mapped[list[TuitionClass]] = relationship(secondary=exam_classes, lazy="selectin")
    parts: Mapped[list[ExamPart]] = relationship(
        back_populates="exam",
        lazy="selectin",
        order_by="ExamPart.position",
        cascade="all, delete-orphan",
    )

    @property
    def class_ids(self) -> list[int]:
        return [c.id for c in self.classes]

    @property
    def max_total(self) -> Decimal:
        return sum((p.max_marks for p in self.parts), Decimal(0))


class ExamPart(IdMixin, TenantMixin, Base):
    """MCQ, Structured, Essay, ..."""

    __tablename__ = "exam_parts"
    __table_args__ = (CheckConstraint("max_marks > 0", name="max_marks_positive"),)

    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    position: Mapped[int] = mapped_column(SmallInteger)

    exam: Mapped[Exam] = relationship(back_populates="parts")


class ExamMark(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "exam_marks"
    __table_args__ = (
        UniqueConstraint("part_id", "student_id"),
        CheckConstraint(
            "(is_absent AND marks IS NULL) OR (NOT is_absent AND marks IS NOT NULL)",
            name="marks_or_absent",
        ),
    )

    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("exam_parts.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_absent: Mapped[bool] = mapped_column(default=False, server_default=false())
    entered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

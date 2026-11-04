from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.classes.models import TuitionClass
from app.modules.teachers.models import Teacher

tute_classes = Table(
    "tute_classes",
    Base.metadata,
    Column("tute_id", ForeignKey("tutes.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
)


class TuteAccess(StrEnum):
    FREE = "free"  # for students who paid that month's class fee
    PAID = "paid"  # also needs the tute price paid, on a receipt


class Tute(IdMixin, TenantMixin, TimestampMixin, Base):
    """Notes or papers for a month. One tute can be used by several classes.

    Who may have it is never stored: it's worked out from payments each time, so voiding a
    receipt takes access away at once.
    """

    __tablename__ = "tutes"
    __table_args__ = (CheckConstraint("access_type = 'free' OR price > 0", name="paid_has_price"),)

    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    number: Mapped[int | None] = mapped_column(Integer)  # "Tute 5"
    month: Mapped[dt.date] = mapped_column(Date, index=True)  # first day of the month
    access_type: Mapped[TuteAccess] = mapped_column(str_enum(TuteAccess), default=TuteAccess.FREE)
    price: Mapped[Decimal | None]
    has_hard_copy: Mapped[bool] = mapped_column(default=True, server_default=true())
    # The soft copy (PDF), if uploaded. `file_path` is a name inside app storage.
    file_path: Mapped[str | None] = mapped_column(String(255))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(Integer)

    teacher: Mapped[Teacher] = relationship(lazy="joined")
    classes: Mapped[list[TuitionClass]] = relationship(secondary=tute_classes, lazy="selectin")

    @property
    def class_ids(self) -> list[int]:
        return [c.id for c in self.classes]

    @property
    def has_file(self) -> bool:
        return self.file_path is not None


class TuteIssue(IdMixin, TenantMixin, TimestampMixin, Base):
    """A hard copy handed to a student (the tick)."""

    __tablename__ = "tute_issues"
    __table_args__ = (UniqueConstraint("tute_id", "student_id"),)

    tute_id: Mapped[int] = mapped_column(ForeignKey("tutes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    issued_at: Mapped[dt.datetime]

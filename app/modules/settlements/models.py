from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.payments.models import PaymentMethod, PaymentStatus
from app.modules.teachers.models import Teacher
from app.modules.users.models import User


class TeacherPayout(IdMixin, TenantMixin, TimestampMixin, Base):
    """Money paid to a teacher for a month. Voided rather than deleted, like receipts."""

    __tablename__ = "teacher_payouts"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    month: Mapped[dt.date] = mapped_column(Date, index=True)  # the month it settles
    amount: Mapped[Decimal]
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod))
    note: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[dt.datetime]
    paid_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus), default=PaymentStatus.VALID
    )
    void_reason: Mapped[str | None] = mapped_column(String(255))
    voided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[dt.datetime | None]

    teacher: Mapped[Teacher] = relationship(lazy="joined")
    paid_by: Mapped[User] = relationship(foreign_keys=[paid_by_id], lazy="joined")
    voided_by: Mapped[User | None] = relationship(foreign_keys=[voided_by_id], lazy="joined")

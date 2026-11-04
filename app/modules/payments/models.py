from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.modules.branches.models import Branch
from app.modules.classes.models import TuitionClass
from app.modules.students.models import CardType, Student
from app.modules.tutes.models import Tute
from app.modules.users.models import User


class PaymentMethod(StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"


class PaymentStatus(StrEnum):
    VALID = "valid"
    VOID = "void"


class ItemKind(StrEnum):
    MONTHLY = "monthly"  # one class, one month
    ADMISSION = "admission"  # once per student
    TUTE = "tute"  # a paid tute


class CashHandover(IdMixin, TenantMixin, TimestampMixin, Base):
    """Cash a collector (a teacher or front-desk staff) hands to the institute."""

    __tablename__ = "cash_handovers"

    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    collected_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    received_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal]
    handed_at: Mapped[datetime]
    note: Mapped[str | None] = mapped_column(String(255))

    branch: Mapped[Branch] = relationship(lazy="joined")
    collected_by: Mapped[User] = relationship(foreign_keys=[collected_by_id], lazy="joined")
    received_by: Mapped[User] = relationship(foreign_keys=[received_by_id], lazy="joined")


class Payment(IdMixin, TenantMixin, TimestampMixin, Base):
    """A receipt. Amounts are worked out by the server from the fee rules, never sent in."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_no"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    receipt_no: Mapped[str] = mapped_column(String(30))  # GAL-000123, numbered per branch
    amount: Mapped[Decimal]
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod))
    paid_at: Mapped[datetime] = mapped_column(index=True)
    collected_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus), default=PaymentStatus.VALID
    )
    void_reason: Mapped[str | None] = mapped_column(String(255))
    voided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None]
    # Set once the cash is handed over (cash payments only).
    handover_id: Mapped[int | None] = mapped_column(ForeignKey("cash_handovers.id"), index=True)

    branch: Mapped[Branch] = relationship(lazy="joined")
    student: Mapped[Student] = relationship(lazy="joined")
    collected_by: Mapped[User] = relationship(foreign_keys=[collected_by_id], lazy="joined")
    voided_by: Mapped[User | None] = relationship(foreign_keys=[voided_by_id], lazy="joined")
    handover: Mapped[CashHandover | None] = relationship()
    items: Mapped[list[PaymentItem]] = relationship(
        back_populates="payment", lazy="selectin", cascade="all, delete-orphan"
    )


class PaymentItem(IdMixin, TenantMixin, Base):
    """One line on a receipt. Keeps the amounts and discounts as they were when paid."""

    __tablename__ = "payment_items"
    __table_args__ = (
        # A month of a class, and the admission fee, can each be paid only once.
        Index(
            "uq_payment_items_month_once",
            "enrollment_id",
            "month",
            unique=True,
            postgresql_where=text("kind = 'monthly' AND NOT voided"),
        ),
        Index(
            "uq_payment_items_admission_once",
            "student_id",
            unique=True,
            postgresql_where=text("kind = 'admission' AND NOT voided"),
        ),
        Index(
            "uq_payment_items_tute_once",
            "student_id",
            "tute_id",
            unique=True,
            postgresql_where=text("kind = 'tute' AND NOT voided"),
        ),
        CheckConstraint("amount >= 0 AND amount <= full_amount", name="amount_in_range"),
    )

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    kind: Mapped[ItemKind] = mapped_column(str_enum(ItemKind))
    enrollment_id: Mapped[int | None] = mapped_column(ForeignKey("enrollments.id"), index=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"), index=True)
    # The class's teacher at the time, for teacher settlements.
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), index=True)
    month: Mapped[date | None] = mapped_column(Date)  # first day of the month paid for
    tute_id: Mapped[int | None] = mapped_column(ForeignKey("tutes.id"), index=True)
    full_amount: Mapped[Decimal]
    amount: Mapped[Decimal]  # what was charged after discounts
    # The institute's cut of `amount` when it was paid, so later changes to a teacher's deal
    # don't rewrite past settlements. Admission is all the institute's (100).
    institute_share_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    card_type: Mapped[CardType | None] = mapped_column(str_enum(CardType))
    late_join: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Copied from the payment so the "pay once" indexes ignore voided receipts.
    voided: Mapped[bool] = mapped_column(default=False, server_default=false())

    payment: Mapped[Payment] = relationship(back_populates="items")
    tuition_class: Mapped[TuitionClass | None] = relationship(lazy="joined")
    tute: Mapped[Tute | None] = relationship(lazy="joined")

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from app.common.repository import TenantScopedRepository
from app.core.config import settings
from app.modules.payments.models import ItemKind, Payment, PaymentItem, PaymentStatus
from app.modules.settlements.models import TeacherPayout


class PayoutRepository(TenantScopedRepository[TeacherPayout]):
    model = TeacherPayout
    label = "Payout"

    def for_teacher(self, teacher_id: int) -> list[TeacherPayout]:
        return self.find(
            TeacherPayout.teacher_id == teacher_id,
            order_by=[TeacherPayout.month.desc(), TeacherPayout.paid_at.desc()],
        )

    def paid_by_teacher(self, month: dt.date | None = None) -> dict[int, Decimal]:
        """Valid payouts per teacher, for one month or all of them."""
        stmt = (
            select(TeacherPayout.teacher_id, func.sum(TeacherPayout.amount))
            .where(
                TeacherPayout.tenant_id == self.ctx.tenant_id,
                TeacherPayout.status == PaymentStatus.VALID,
            )
            .group_by(TeacherPayout.teacher_id)
        )
        if month is not None:
            stmt = stmt.where(TeacherPayout.month == month)
        return dict(self.db.execute(stmt).all())

    def paid_by_month(self, teacher_id: int) -> dict[dt.date, Decimal]:
        stmt = (
            select(TeacherPayout.month, func.sum(TeacherPayout.amount))
            .where(
                TeacherPayout.tenant_id == self.ctx.tenant_id,
                TeacherPayout.status == PaymentStatus.VALID,
                TeacherPayout.teacher_id == teacher_id,
            )
            .group_by(TeacherPayout.month)
        )
        return dict(self.db.execute(stmt).all())


class CollectionRepository:
    """Teachers' money on valid receipts: class fees and paid tutes, by when it was received."""

    def __init__(self, db, ctx) -> None:
        self.db = db
        self.ctx = ctx

    def _base(self):
        return (
            select()
            .select_from(PaymentItem)
            .join(Payment, Payment.id == PaymentItem.payment_id)
            .where(
                PaymentItem.tenant_id == self.ctx.tenant_id,
                PaymentItem.voided.is_(False),
                PaymentItem.teacher_id.is_not(None),
                PaymentItem.kind.in_([ItemKind.MONTHLY, ItemKind.TUTE]),
            )
        )

    @staticmethod
    def _sums():
        return (
            func.sum(PaymentItem.amount),
            func.sum(PaymentItem.amount * PaymentItem.institute_share_percent / 100),
        )

    def by_teacher(self, start: dt.datetime, end: dt.datetime) -> list[tuple]:
        """(teacher_id, kind, collected, institute part) received in [start, end)."""
        stmt = (
            self._base()
            .add_columns(PaymentItem.teacher_id, PaymentItem.kind, *self._sums())
            .where(Payment.paid_at >= start, Payment.paid_at < end)
            .group_by(PaymentItem.teacher_id, PaymentItem.kind)
        )
        return list(self.db.execute(stmt).all())

    def by_month(self, teacher_id: int) -> list[tuple]:
        """(month, collected, institute part) for one teacher, every month (local time)."""
        local = func.timezone(settings.timezone, Payment.paid_at)
        month = func.date_trunc("month", local).label("month")
        stmt = (
            self._base()
            .add_columns(month, *self._sums())
            .where(PaymentItem.teacher_id == teacher_id)
            .group_by(month)
        )
        return [(m.date(), collected, part) for m, collected, part in self.db.execute(stmt).all()]

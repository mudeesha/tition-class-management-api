import datetime as dt

from sqlalchemy import func, select

from app.core.config import settings
from app.modules.payments.models import Payment, PaymentItem, PaymentStatus


class MoneyRepository:
    """Totals of valid receipts, limited to the branches the member can see."""

    def __init__(self, db, ctx) -> None:
        self.db = db
        self.ctx = ctx

    def _where(self, start: dt.datetime, end: dt.datetime, branch_id: int | None):
        where = [
            Payment.tenant_id == self.ctx.tenant_id,
            Payment.status == PaymentStatus.VALID,
            Payment.paid_at >= start,
            Payment.paid_at < end,
        ]
        if not self.ctx.all_branches:
            where.append(Payment.branch_id.in_(self.ctx.branch_ids))
        if branch_id is not None:
            where.append(Payment.branch_id == branch_id)
        return where

    def by_day_and_method(self, start, end, branch_id) -> list[tuple]:
        """(local date, method, receipts, total)."""
        day = func.date(func.timezone(settings.timezone, Payment.paid_at)).label("day")
        stmt = (
            select(day, Payment.method, func.count(), func.sum(Payment.amount))
            .where(*self._where(start, end, branch_id))
            .group_by(day, Payment.method)
        )
        return list(self.db.execute(stmt).all())

    def by_kind(self, start, end, branch_id) -> dict:
        stmt = (
            select(PaymentItem.kind, func.sum(PaymentItem.amount))
            .join(Payment, Payment.id == PaymentItem.payment_id)
            .where(*self._where(start, end, branch_id))
            .group_by(PaymentItem.kind)
        )
        return dict(self.db.execute(stmt).all())

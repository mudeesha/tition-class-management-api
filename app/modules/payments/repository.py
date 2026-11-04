from datetime import date, datetime

from sqlalchemy import Select, func, select

from app.common.repository import BranchScopedRepository
from app.modules.payments.models import (
    CashHandover,
    ItemKind,
    Payment,
    PaymentItem,
    PaymentMethod,
    PaymentStatus,
)


class PaymentRepository(BranchScopedRepository[Payment]):
    model = Payment
    label = "Receipt"

    def search(
        self,
        q: str | None,
        branch_id: int | None,
        student_id: int | None,
        status: PaymentStatus | None,
        collected_by_id: int | None,
        paid_from: datetime | None,
        paid_before: datetime | None,
    ) -> Select[tuple[Payment]]:
        stmt = self.query()
        if q:
            stmt = stmt.where(func.lower(Payment.receipt_no).like(f"%{q.lower()}%"))
        filters = {
            Payment.branch_id: branch_id,
            Payment.student_id: student_id,
            Payment.status: status,
            Payment.collected_by_id: collected_by_id,
        }
        for column, value in filters.items():
            if value is not None:
                stmt = stmt.where(column == value)
        if paid_from is not None:
            stmt = stmt.where(Payment.paid_at >= paid_from)
        if paid_before is not None:
            stmt = stmt.where(Payment.paid_at < paid_before)
        return stmt.order_by(Payment.paid_at.desc(), Payment.id.desc())

    def paid_months(self, enrollment_ids: list[int]) -> set[tuple[int, date]]:
        """(enrollment, month) pairs covered by a valid receipt."""
        if not enrollment_ids:
            return set()
        stmt = select(PaymentItem.enrollment_id, PaymentItem.month).where(
            PaymentItem.tenant_id == self.ctx.tenant_id,
            PaymentItem.kind == ItemKind.MONTHLY,
            PaymentItem.voided.is_(False),
            PaymentItem.enrollment_id.in_(enrollment_ids),
        )
        return {(e, m) for e, m in self.db.execute(stmt).all()}

    def admission_paid(self, student_id: int) -> bool:
        stmt = select(PaymentItem.id).where(
            PaymentItem.tenant_id == self.ctx.tenant_id,
            PaymentItem.kind == ItemKind.ADMISSION,
            PaymentItem.voided.is_(False),
            PaymentItem.student_id == student_id,
        )
        return self.db.scalar(stmt.limit(1)) is not None

    def tutes_bought(self, student_id: int | None = None, tute_id: int | None = None):
        """(student, tute) pairs with a valid receipt for a paid tute."""
        stmt = select(PaymentItem.student_id, PaymentItem.tute_id).where(
            PaymentItem.tenant_id == self.ctx.tenant_id,
            PaymentItem.kind == ItemKind.TUTE,
            PaymentItem.voided.is_(False),
        )
        if student_id is not None:
            stmt = stmt.where(PaymentItem.student_id == student_id)
        if tute_id is not None:
            stmt = stmt.where(PaymentItem.tute_id == tute_id)
        return {(s, t) for s, t in self.db.execute(stmt).all()}

    def cash_not_handed_over(
        self, collected_by_id: int | None = None, branch_id: int | None = None
    ) -> list[Payment]:
        where = [
            Payment.method == PaymentMethod.CASH,
            Payment.status == PaymentStatus.VALID,
            Payment.handover_id.is_(None),
        ]
        if collected_by_id is not None:
            where.append(Payment.collected_by_id == collected_by_id)
        if branch_id is not None:
            where.append(Payment.branch_id == branch_id)
        return self.find(*where, order_by=[Payment.paid_at])


class HandoverRepository(BranchScopedRepository[CashHandover]):
    model = CashHandover
    label = "Handover"

    def search(self, branch_id: int | None, collected_by_id: int | None):
        stmt = self.query()
        if branch_id is not None:
            stmt = stmt.where(CashHandover.branch_id == branch_id)
        if collected_by_id is not None:
            stmt = stmt.where(CashHandover.collected_by_id == collected_by_id)
        return stmt.order_by(CashHandover.handed_at.desc(), CashHandover.id.desc())

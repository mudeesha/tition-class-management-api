from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.schemas import add_months, month_of
from app.core import clock
from app.core.exceptions import Forbidden, RuleViolation
from app.modules.classes.schemas import TeacherRef
from app.modules.payments.models import ItemKind, PaymentStatus
from app.modules.settlements.models import TeacherPayout
from app.modules.settlements.repository import CollectionRepository, PayoutRepository
from app.modules.settlements.schemas import (
    PayoutCreate,
    PayoutOut,
    SettlementOut,
    SettlementRow,
    TeacherMonth,
    TeacherSettlementOut,
    VoidIn,
)
from app.modules.teachers.models import Teacher
from app.modules.teachers.repository import TeacherRepository
from app.tenancy.context import TenantContext

CENT = Decimal("0.01")
ZERO = Decimal(0)


def _money(value) -> Decimal:
    return (value or ZERO).quantize(CENT)


class SettlementService:
    """What each teacher earned and was paid.

    A month's collections are the teacher's class fees and paid tutes on valid receipts
    received in that month. The institute's share uses the % saved on each receipt line.
    """

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        if not ctx.all_branches:
            # Teachers are paid for all their branches at once.
            raise Forbidden("Settlements need access to all branches")
        self.db = db
        self.ctx = ctx
        self.payouts = PayoutRepository(db, ctx)
        self.collections = CollectionRepository(db, ctx)
        self.teachers = TeacherRepository(db, ctx)

    def month(self, month: dt.date) -> SettlementOut:
        start = dt.datetime.combine(month, dt.time(), tzinfo=clock.now().tzinfo)
        end = dt.datetime.combine(add_months(month, 1), dt.time(), tzinfo=clock.now().tzinfo)

        sums: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for teacher_id, kind, collected, part in self.collections.by_teacher(start, end):
            key = "class_fees" if kind == ItemKind.MONTHLY else "tutes"
            sums[teacher_id][key] += collected
            sums[teacher_id]["institute"] += part
        paid = self.payouts.paid_by_teacher(month)

        wanted = set(sums) | set(paid)
        teachers = [
            t for t in self.teachers.find(order_by=[Teacher.name]) if t.is_active or t.id in wanted
        ]
        rows = []
        for t in teachers:
            s = sums.get(t.id, {})
            collected = _money(s.get("class_fees", ZERO) + s.get("tutes", ZERO))
            institute = _money(s.get("institute"))
            teacher_share = collected - institute
            rows.append(
                SettlementRow(
                    teacher=TeacherRef.model_validate(t),
                    share_percent=t.institute_share_percent,
                    class_fees=_money(s.get("class_fees")),
                    tutes=_money(s.get("tutes")),
                    collected=collected,
                    institute_share=institute,
                    teacher_share=teacher_share,
                    paid=_money(paid.get(t.id)),
                    balance=teacher_share - _money(paid.get(t.id)),
                )
            )
        return SettlementOut(
            month=month,
            rows=rows,
            collected=sum((r.collected for r in rows), ZERO),
            institute_share=sum((r.institute_share for r in rows), ZERO),
            teacher_share=sum((r.teacher_share for r in rows), ZERO),
            paid=sum((r.paid for r in rows), ZERO),
        )

    def teacher(self, teacher_id: int) -> TeacherSettlementOut:
        """Month by month, latest first, plus everything still owed to date."""
        teacher = self.teachers.get_or_404(teacher_id)
        earned = {
            m: (collected, part) for m, collected, part in self.collections.by_month(teacher.id)
        }
        paid = self.payouts.paid_by_month(teacher.id)
        months = sorted(set(earned) | set(paid), reverse=True)

        rows, owed = [], ZERO
        for m in months:
            collected, part = earned.get(m, (ZERO, ZERO))
            share = _money(collected) - _money(part)
            owed += share - _money(paid.get(m))
            rows.append(
                TeacherMonth(
                    month=m,
                    collected=_money(collected),
                    teacher_share=share,
                    paid=_money(paid.get(m)),
                )
            )
        return TeacherSettlementOut(
            teacher=TeacherRef.model_validate(teacher),
            share_percent=teacher.institute_share_percent,
            owed=owed,
            months=rows,
            payouts=[PayoutOut.model_validate(p) for p in self.payouts.for_teacher(teacher.id)],
        )

    def pay(self, data: PayoutCreate) -> TeacherPayout:
        teacher = self.teachers.get_or_404(data.teacher_id)
        if data.month > add_months(month_of(clock.today()), 1):
            raise RuleViolation("Payouts can be for past months, this month or next month")
        payout = self.payouts.add(
            TeacherPayout(
                teacher=teacher,
                month=data.month,
                amount=data.amount,
                method=data.method,
                note=data.note,
                paid_at=clock.now(),
                paid_by=self.ctx.user,
            )
        )
        self.db.commit()
        return payout

    def void(self, payout_id: int, data: VoidIn) -> TeacherPayout:
        payout = self.payouts.get_or_404(payout_id)
        if payout.status == PaymentStatus.VOID:
            raise RuleViolation("This payout is already void")
        payout.status = PaymentStatus.VOID
        payout.void_reason = data.reason
        payout.voided_by = self.ctx.user
        payout.voided_at = clock.now()
        self.db.commit()
        return payout

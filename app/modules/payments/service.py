from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams, add_months, month_of
from app.core import clock
from app.core.exceptions import Conflict, Forbidden, NotFound, RuleViolation
from app.modules.branches.repository import BranchRepository
from app.modules.institute.models import InstituteSettings
from app.modules.institute.repository import CounterRepository, InstituteSettingsRepository
from app.modules.payments.fees import attends_in, month_charge, months
from app.modules.payments.models import (
    CashHandover,
    ItemKind,
    Payment,
    PaymentItem,
    PaymentStatus,
)
from app.modules.payments.repository import HandoverRepository, PaymentRepository
from app.modules.payments.schemas import (
    CashInHandOut,
    DueMonth,
    DuesOut,
    DueTute,
    HandoverCreate,
    PaymentCreate,
    VoidIn,
)
from app.modules.students.models import Enrollment
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.tutes.models import TuteAccess
from app.modules.tutes.repository import TuteRepository
from app.modules.users.repository import UserRepository
from app.tenancy.context import TenantContext

# Paying ahead is allowed, but not without limit.
MONTHS_AHEAD = 12


def month_name(month: date) -> str:
    return month.strftime("%B %Y")


class FeeRules:
    """Applies the institute's fee settings to enrollments and receipts."""

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.payments = PaymentRepository(db, ctx)
        self._settings = InstituteSettingsRepository(db, ctx)

    @property
    def settings(self) -> InstituteSettings:
        return self._settings.current()

    def paid_for(self, enrollments: list[Enrollment], month: date) -> set[int]:
        """Ids of the enrollments whose month is paid, or has nothing to pay (free card)."""
        settings = self.settings
        paid = self.payments.paid_months([e.id for e in enrollments])
        return {
            e.id
            for e in enrollments
            if (e.id, month) in paid or month_charge(e, month, settings).amount == 0
        }


class PaymentService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.payments = PaymentRepository(db, ctx)
        self.students = StudentRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)
        self.counters = CounterRepository(db, ctx)
        self.settings = InstituteSettingsRepository(db, ctx)
        self.tutes = TuteRepository(db, ctx)

    # What is owed

    def dues(self, student_id: int, until: date | None = None) -> DuesOut:
        """Unpaid months up to `until` (default: this month) and the admission fee if unpaid.

        Only classes in branches the caller can see.
        """
        student = self.students.get_or_404(student_id)
        settings = self.settings.current()
        until = until or month_of(clock.today())

        enrollments = self.enrollments.for_student(student.id)
        paid = self.payments.paid_months([e.id for e in enrollments])
        due = []
        for e in enrollments:
            last = min(e.end_month or until, until)
            for month in months(e.start_month, last):
                if (e.id, month) in paid:
                    continue
                charge = month_charge(e, month, settings)
                if charge.amount > 0:
                    due.append(
                        DueMonth(
                            enrollment_id=e.id,
                            tuition_class=e.tuition_class,
                            month=month,
                            full_amount=charge.full_amount,
                            amount=charge.amount,
                            card_type=charge.card_type,
                            late_join=charge.late_join,
                        )
                    )
        due.sort(key=lambda d: (d.month, d.tuition_class.title))

        admission = None
        if settings.admission_fee > 0 and not self.payments.admission_paid(student.id):
            admission = settings.admission_fee
        total = sum((d.amount for d in due), admission or Decimal(0))
        return DuesOut(
            admission_fee=admission,
            months=due,
            total=total,
            tutes=self._tutes_to_buy(student.id, enrollments, until),
        )

    def _tutes_to_buy(
        self, student_id: int, enrollments: list[Enrollment], until: date
    ) -> list[DueTute]:
        bought = {t for _, t in self.payments.tutes_bought(student_id=student_id)}
        result = []
        for tute in self.tutes.for_classes([e.class_id for e in enrollments]):
            if tute.access_type != TuteAccess.PAID or tute.id in bought or tute.month > until:
                continue
            attends = any(
                e.class_id in tute.class_ids and attends_in(e, tute.month) for e in enrollments
            )
            if attends:
                result.append(
                    DueTute(tute_id=tute.id, title=tute.title, month=tute.month, price=tute.price)
                )
        return sorted(result, key=lambda t: (t.month, t.title))

    # Receipts

    def list(
        self,
        page: PageParams,
        q: str | None,
        branch_id: int | None,
        student_id: int | None,
        status: PaymentStatus | None,
        collected_by_id: int | None,
        date_from: date | None,
        date_to: date | None,
    ) -> Page:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        stmt = self.payments.search(
            q,
            branch_id,
            student_id,
            status,
            collected_by_id,
            self._start_of(date_from) if date_from else None,
            self._start_of(date_to + timedelta(days=1)) if date_to else None,
        )
        items, total = self.payments.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, payment_id: int) -> Payment:
        return self.payments.get_or_404(payment_id)

    def create(self, data: PaymentCreate) -> Payment:
        student = self.students.get_or_404(data.student_id)
        branch = self.branches.get_or_404(data.branch_id)
        settings = self.settings.current()
        latest = add_months(month_of(clock.today()), MONTHS_AHEAD)

        items: list[PaymentItem] = []
        wanted: set[tuple[int, date]] = set()
        for line in data.items:
            if line.kind == ItemKind.ADMISSION:
                if any(i.kind == ItemKind.ADMISSION for i in items):
                    raise RuleViolation("The admission fee is listed twice")
                if settings.admission_fee <= 0:
                    raise RuleViolation("This institute has no admission fee")
                if self.payments.admission_paid(student.id):
                    raise Conflict(f"{student.name}'s admission fee is already paid")
                items.append(
                    PaymentItem(
                        kind=ItemKind.ADMISSION,
                        student_id=student.id,
                        full_amount=settings.admission_fee,
                        amount=settings.admission_fee,
                        institute_share_percent=Decimal(100),
                    )
                )
                continue

            if line.kind == ItemKind.TUTE:
                items.append(self._tute_item(line.tute_id, student, branch.id, items))
                continue

            enrollment = self.enrollments.get_or_404(line.enrollment_id)
            cls = enrollment.tuition_class
            what = f"{cls.title} for {month_name(line.month)}"
            if enrollment.student_id != student.id:
                raise RuleViolation(f"{student.name} is not in {cls.title}")
            if enrollment.branch_id != branch.id:
                raise RuleViolation(f"{cls.title} is paid at the {cls.branch.name} branch")
            if not attends_in(enrollment, line.month):
                raise RuleViolation(f"{student.name} is not in {what}")
            if line.month > latest:
                raise RuleViolation(f"Fees can be paid up to {MONTHS_AHEAD} months ahead")
            if (enrollment.id, line.month) in wanted:
                raise RuleViolation(f"{what} is listed twice")
            wanted.add((enrollment.id, line.month))

            charge = month_charge(enrollment, line.month, settings)
            if charge.amount == 0:
                raise RuleViolation(f"There is nothing to pay for {what}")
            items.append(
                PaymentItem(
                    kind=ItemKind.MONTHLY,
                    student_id=student.id,
                    enrollment_id=enrollment.id,
                    class_id=cls.id,
                    teacher_id=cls.teacher_id,
                    month=line.month,
                    full_amount=charge.full_amount,
                    amount=charge.amount,
                    card_type=charge.card_type,
                    late_join=charge.late_join,
                    institute_share_percent=cls.teacher.institute_share_percent,
                )
            )

        already = self.payments.paid_months([e for e, _ in wanted]) & wanted
        if already:
            enrollment_id, month = sorted(already)[0]
            title = self.enrollments.get_or_404(enrollment_id).tuition_class.title
            raise Conflict(f"{title} for {month_name(month)} is already paid")

        payment = Payment(
            branch=branch,
            student=student,
            receipt_no=self._next_receipt_no(branch.id, branch.code),
            amount=sum(i.amount for i in items),
            method=data.method,
            paid_at=clock.now(),
            collected_by_id=self.ctx.user.id,
            note=data.note,
            items=items,
        )
        for item in items:
            item.tenant_id = self.ctx.tenant_id
        self.payments.add(payment)
        self.db.commit()
        return payment

    def void(self, payment_id: int, data: VoidIn) -> Payment:
        """The months on a voided receipt count as unpaid again."""
        payment = self.get(payment_id)
        if payment.status == PaymentStatus.VOID:
            raise RuleViolation("This receipt is already void")
        payment.status = PaymentStatus.VOID
        payment.void_reason = data.reason
        payment.voided_by = self.ctx.user
        payment.voided_at = clock.now()
        for item in payment.items:
            item.voided = True
        self.db.commit()
        return payment

    def _tute_item(
        self, tute_id: int, student, branch_id: int, items: list[PaymentItem]
    ) -> PaymentItem:
        """A paid tute, bought by a student of one of its classes at this branch."""
        tute = self.tutes.get_or_404(tute_id)
        if tute.access_type != TuteAccess.PAID:
            raise RuleViolation(f"{tute.title} is free")
        if any(i.tute_id == tute.id for i in items):
            raise RuleViolation(f"{tute.title} is listed twice")
        if (student.id, tute.id) in self.payments.tutes_bought(student_id=student.id):
            raise Conflict(f"{student.name} has already paid for {tute.title}")
        here = [
            e
            for e in self.enrollments.attending(tute.class_ids, tute.month, student.id)
            if e.branch_id == branch_id
        ]
        if not here:
            raise RuleViolation(
                f"{student.name} isn't in a class at this branch that uses {tute.title}"
            )
        return PaymentItem(
            kind=ItemKind.TUTE,
            student_id=student.id,
            tute_id=tute.id,
            class_id=here[0].class_id,
            teacher_id=tute.teacher_id,
            month=tute.month,
            full_amount=tute.price,
            amount=tute.price,
            institute_share_percent=self.settings.current().tute_institute_share_percent,
        )

    def _next_receipt_no(self, branch_id: int, branch_code: str) -> str:
        return f"{branch_code}-{self.counters.next(f'receipt:{branch_id}'):06d}"

    @staticmethod
    def _start_of(day: date) -> datetime:
        return datetime.combine(day, datetime.min.time(), tzinfo=clock.now().tzinfo)


class CashService:
    """Cash collected by each person that hasn't been handed over yet."""

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.payments = PaymentRepository(db, ctx)
        self.handovers = HandoverRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)
        self.users = UserRepository(db)

    def in_hand(self, branch_id: int | None) -> list[CashInHandOut]:
        """Everyone's cash for people who receive it; otherwise only your own."""
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        mine_only = None if self.ctx.has("cash.receive") else self.ctx.user.id
        groups: dict[tuple[int, int], list[Payment]] = defaultdict(list)
        for p in self.payments.cash_not_handed_over(mine_only, branch_id):
            groups[(p.collected_by_id, p.branch_id)].append(p)
        return [
            CashInHandOut(
                collected_by=group[0].collected_by,
                branch=group[0].branch,
                amount=sum(p.amount for p in group),
                receipts=len(group),
            )
            for group in sorted(
                groups.values(), key=lambda g: (g[0].branch.name, g[0].collected_by.name)
            )
        ]

    def hand_over(self, data: HandoverCreate) -> CashHandover:
        """Takes over all of one person's cash at one branch, as of now."""
        if not self.ctx.has("cash.receive"):
            raise Forbidden("You need the 'cash.receive' permission", code="permission_denied")
        if data.collected_by_id == self.ctx.user.id:
            raise RuleViolation("Someone else has to take over your cash")
        branch = self.branches.get_or_404(data.branch_id)
        payments = self.payments.cash_not_handed_over(data.collected_by_id, branch.id)
        if not payments:
            raise RuleViolation("There is no cash to hand over")
        collector = self.users.get(data.collected_by_id)
        if collector is None:
            raise NotFound("User not found")

        handover = CashHandover(
            branch=branch,
            collected_by=collector,
            received_by=self.ctx.user,
            amount=sum(p.amount for p in payments),
            handed_at=clock.now(),
            note=data.note,
        )
        self.handovers.add(handover)
        for p in payments:
            p.handover = handover
        self.db.commit()
        return handover

    def history(self, page: PageParams, branch_id: int | None, collected_by_id: int | None) -> Page:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        stmt = self.handovers.search(branch_id, collected_by_id)
        items, total = self.handovers.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

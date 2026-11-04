from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.schemas import add_months, month_of
from app.core import clock
from app.core.exceptions import RuleViolation
from app.modules.attendance.models import SessionStatus
from app.modules.attendance.service import SessionService
from app.modules.payments.fees import month_charge, months
from app.modules.payments.models import ItemKind, PaymentMethod
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.service import FeeRules
from app.modules.reports.repository import MoneyRepository
from app.modules.reports.schemas import (
    AttendanceReport,
    ClassAttendance,
    CollectionDay,
    CollectionsReport,
    DashboardOut,
    DueRow,
    DuesReport,
    StudentContact,
    TodayAttendance,
    Unpaid,
)
from app.modules.students.models import Enrollment
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.tenancy.context import TenantContext

ZERO = Decimal(0)
MAX_DAYS = 93


def _start(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(), tzinfo=clock.now().tzinfo)


class ReportService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.money = MoneyRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.students = StudentRepository(db, ctx)
        self.payments = PaymentRepository(db, ctx)
        self.fees = FeeRules(db, ctx)
        self.days = SessionService(db, ctx)

    # The dashboard

    def dashboard(self, branch_id: int | None) -> DashboardOut:
        """Each part only for people with the permission behind it."""
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        today = clock.today()
        month = month_of(today)
        out = DashboardOut(date=today)

        if self.ctx.has("attendance.view"):
            classes = self.days.list(today, today, branch_id=branch_id)
            out.classes_today = classes
            out.attendance_today = TodayAttendance(
                came=sum(s.counts.present + s.counts.late for s in classes),
                absent=sum(s.counts.absent for s in classes),
            )
        if self.ctx.has("payments.view"):
            tomorrow = today + dt.timedelta(days=1)
            rows = self.money.by_day_and_method(_start(today), _start(tomorrow), branch_id)
            out.collected_today = sum((r[3] for r in rows), ZERO)
            out.receipts_today = sum(r[2] for r in rows)
            month_rows = self.money.by_day_and_method(
                _start(month), _start(add_months(month, 1)), branch_id
            )
            out.collected_this_month = sum((r[3] for r in month_rows), ZERO)
            out.cash_not_handed_over = sum(
                (p.amount for p in self.payments.cash_not_handed_over(None, branch_id)), ZERO
            )
            unpaid = self._unpaid_in(month, branch_id)
            out.unpaid_this_month = Unpaid(
                students=len({e.student_id for e, _ in unpaid}),
                amount=sum((amount for _, amount in unpaid), ZERO),
            )
        if self.ctx.has("students.view"):
            out.active_students = self.students.count_active()
        return out

    # Reports

    def dues(self, branch_id: int | None, class_id: int | None) -> DuesReport:
        """Everyone who owes class fees up to this month, most owed first."""
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        until = month_of(clock.today())
        where = [Enrollment.start_month <= until]
        if branch_id is not None:
            where.append(Enrollment.branch_id == branch_id)
        if class_id is not None:
            where.append(Enrollment.class_id == class_id)
        enrollments = [e for e in self.enrollments.find(*where) if e.student.is_active]
        paid = self.payments.paid_months([e.id for e in enrollments])
        settings = self.fees.settings

        rows = []
        for e in enrollments:
            owed, amount = [], ZERO
            for m in months(e.start_month, min(e.end_month or until, until)):
                if (e.id, m) in paid:
                    continue
                charge = month_charge(e, m, settings).amount
                if charge > 0:
                    owed.append(m)
                    amount += charge
            if owed:
                rows.append(
                    DueRow(
                        student=StudentContact.model_validate(e.student),
                        tuition_class=e.tuition_class,
                        months=owed,
                        amount=amount,
                    )
                )
        rows.sort(key=lambda r: (-r.amount, r.student.name))
        return DuesReport(until=until, rows=rows, total=sum((r.amount for r in rows), ZERO))

    def collections(
        self, date_from: dt.date, date_to: dt.date, branch_id: int | None
    ) -> CollectionsReport:
        if date_to < date_from:
            raise RuleViolation("The end date is before the start date")
        if (date_to - date_from).days >= MAX_DAYS:
            raise RuleViolation(f"Look at up to {MAX_DAYS} days at a time")
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        start, end = _start(date_from), _start(date_to + dt.timedelta(days=1))

        days: dict[dt.date, dict] = defaultdict(lambda: defaultdict(Decimal))
        for day, method, receipts, total in self.money.by_day_and_method(start, end, branch_id):
            days[day]["receipts"] += receipts
            days[day]["total"] += total
            days[day][PaymentMethod(method).value] += total
        kinds = self.money.by_kind(start, end, branch_id)
        return CollectionsReport(
            days=[
                CollectionDay(
                    date=day,
                    receipts=int(d["receipts"]),
                    total=d["total"],
                    cash=d["cash"],
                    card=d["card"],
                    bank_transfer=d["bank_transfer"],
                )
                for day, d in sorted(days.items())
            ],
            class_fees=kinds.get(ItemKind.MONTHLY, ZERO),
            admission=kinds.get(ItemKind.ADMISSION, ZERO),
            tutes=kinds.get(ItemKind.TUTE, ZERO),
            total=sum(kinds.values(), ZERO),
        )

    def attendance(self, month: dt.date, branch_id: int | None) -> AttendanceReport:
        """Per class: days held so far that month and how many came."""
        today = clock.today()
        last = min(add_months(month, 1) - dt.timedelta(days=1), today)
        if last < month:
            return AttendanceReport(month=month, rows=[])
        held = [
            s
            for s in self.days.list(month, last, branch_id=branch_id)
            if s.status == SessionStatus.SCHEDULED
        ]
        by_class: dict[int, list] = defaultdict(list)
        for s in held:
            by_class[s.tuition_class.id].append(s)
        sizes: dict[int, int] = defaultdict(int)
        for e in self.enrollments.attending(list(by_class), month):
            sizes[e.class_id] += 1

        rows = []
        for class_id, sessions in by_class.items():
            came = sum(s.counts.present + s.counts.late for s in sessions)
            possible = sizes[class_id] * len(sessions)
            rows.append(
                ClassAttendance(
                    tuition_class=sessions[0].tuition_class,
                    days=len(sessions),
                    students=sizes[class_id],
                    came=came,
                    absent=sum(s.counts.absent for s in sessions),
                    rate=(Decimal(came * 100) / possible).quantize(Decimal("0.1"))
                    if possible
                    else None,
                )
            )
        rows.sort(key=lambda r: r.tuition_class.title)
        return AttendanceReport(month=month, rows=rows)

    def _unpaid_in(self, month: dt.date, branch_id: int | None) -> list[tuple[Enrollment, Decimal]]:
        where = [Enrollment.start_month <= month]
        if branch_id is not None:
            where.append(Enrollment.branch_id == branch_id)
        enrollments = [
            e
            for e in self.enrollments.find(*where)
            if (e.end_month is None or e.end_month >= month) and e.student.is_active
        ]
        paid = self.fees.paid_for(enrollments, month)
        settings = self.fees.settings
        return [
            (e, month_charge(e, month, settings).amount) for e in enrollments if e.id not in paid
        ]

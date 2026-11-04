from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.common.schemas import month_of
from app.core import clock
from app.core.exceptions import NotFound, RuleViolation
from app.modules.attendance.models import (
    Attendance,
    AttendanceMethod,
    AttendanceStatus,
    ClassSession,
    FeeStatus,
    SessionKind,
    SessionStatus,
)
from app.modules.attendance.repository import AttendanceRepository, SessionRepository
from app.modules.attendance.schemas import (
    AttendanceMark,
    ExtraSessionIn,
    MarkAllIn,
    RosterRow,
    ScanIn,
    ScanOut,
    SessionCounts,
    SessionOut,
    SessionRef,
    SessionUpdate,
)
from app.modules.branches.repository import BranchRepository, HallRepository
from app.modules.classes.models import TuitionClass
from app.modules.classes.repository import ClassRepository
from app.modules.holidays.repository import HolidayRepository
from app.modules.payments.fees import attends_in, month_charge
from app.modules.payments.service import FeeRules, month_name
from app.modules.students.models import Enrollment, Student
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.students.schemas import StudentRef
from app.tenancy.context import TenantContext

MAX_DAYS = 62
# Scanned in this long after the start counts as late.
LATE_AFTER = dt.timedelta(minutes=15)
# A scan this long before a class starts counts for that class.
EARLY_SCAN = dt.timedelta(minutes=60)


def _local_date(moment: dt.datetime) -> dt.date:
    return moment.astimezone(clock.now().tzinfo).date()


class SessionService:
    """Class days. Regular ones are made from the weekly times the first time a range is
    looked at (skipping holidays); after that they can be cancelled or moved."""

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.sessions = SessionRepository(db, ctx)
        self.attendance = AttendanceRepository(db, ctx)
        self.classes = ClassRepository(db, ctx)
        self.halls = HallRepository(db, ctx)
        self.holidays = HolidayRepository(db, ctx)

    def list(
        self,
        date_from: dt.date,
        date_to: dt.date,
        class_id: int | None = None,
        branch_id: int | None = None,
    ) -> list[SessionOut]:
        if date_to < date_from:
            raise RuleViolation("The end date is before the start date")
        if (date_to - date_from).days >= MAX_DAYS:
            raise RuleViolation(f"Look at up to {MAX_DAYS} days at a time")
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        where = [TuitionClass.is_active.is_(True)]
        if class_id is not None:
            self.classes.get_or_404(class_id)
            where.append(TuitionClass.id == class_id)
        if branch_id is not None:
            where.append(TuitionClass.branch_id == branch_id)
        self.make_days(date_from, date_to, self.classes.find(*where))
        self.db.commit()

        sessions = self.sessions.between(date_from, date_to, class_id, branch_id)
        return self._out(sessions)

    def get(self, session_id: int) -> ClassSession:
        return self.sessions.get_or_404(session_id)

    def detail(self, session_id: int) -> SessionOut:
        return self._out([self.get(session_id)])[0]

    def add_extra(self, class_id: int, data: ExtraSessionIn) -> SessionOut:
        cls = self.classes.get_or_404(class_id)
        if not cls.is_active:
            raise RuleViolation(f"{cls.title} is closed")
        hall_id = data.hall_id if "hall_id" in data.model_fields_set else cls.hall_id
        if hall_id is not None:
            self._check_hall(hall_id, cls.branch_id)
        self._check_clashes(cls, data.date, data.start_time, data.end_time, hall_id)
        session = self.sessions.add(
            ClassSession(
                class_id=cls.id,
                branch_id=cls.branch_id,
                date=data.date,
                start_time=data.start_time,
                end_time=data.end_time,
                hall_id=hall_id,
                kind=SessionKind.EXTRA,
                note=data.note,
            )
        )
        self.db.commit()
        return self._out([session])[0]

    def update(self, session_id: int, data: SessionUpdate) -> SessionOut:
        session = self.get(session_id)
        changes = data.changes()
        marked = bool(self.attendance.for_session(session.id))

        if changes.get("status") == SessionStatus.CANCELLED and marked:
            raise RuleViolation("Attendance is already marked for this day")
        start = changes.get("start_time", session.start_time)
        end = changes.get("end_time", session.end_time)
        if end <= start:
            raise RuleViolation("The end time must be after the start time")
        hall_id = changes.get("hall_id", session.hall_id)
        if "hall_id" in changes and hall_id is not None:
            self._check_hall(hall_id, session.branch_id)
        moved = {"start_time", "end_time", "hall_id"} & changes.keys()
        restored = changes.get("status") == SessionStatus.SCHEDULED
        if (moved or restored) and changes.get("status") != SessionStatus.CANCELLED:
            self._check_clashes(
                session.tuition_class, session.date, start, end, hall_id, session.id
            )

        for field, value in changes.items():
            setattr(session, field, value)
        self.db.commit()
        return self._out([session])[0]

    def make_days(self, date_from: dt.date, date_to: dt.date, classes: list[TuitionClass]) -> None:
        """Creates the regular days of these classes in the range that don't exist yet."""
        off = {(h.branch_id, h.date) for h in self.holidays.between(date_from, date_to)}
        today = clock.today()
        rows = []
        day = date_from
        while day <= date_to:
            for cls in classes:
                # Past days only from when the class was set up.
                if day < today and day < _local_date(cls.created_at):
                    continue
                if (None, day) in off or (cls.branch_id, day) in off:
                    continue
                for s in cls.schedules:
                    if s.weekday == day.isoweekday():
                        rows.append(
                            {
                                "class_id": cls.id,
                                "branch_id": cls.branch_id,
                                "schedule_id": s.id,
                                "date": day,
                                "start_time": s.start_time,
                                "end_time": s.end_time,
                                "hall_id": s.hall_id,
                            }
                        )
            day += dt.timedelta(days=1)
        self.sessions.create_missing(rows)

    def _check_clashes(
        self,
        cls: TuitionClass,
        day: dt.date,
        start: dt.time,
        end: dt.time,
        hall_id: int | None,
        exclude_id: int | None = None,
    ) -> None:
        # Make that day's regular classes first, in every branch, so they are checked too.
        self.make_days(day, day, self.classes.active_in_tenant())
        for other in self.sessions.overlapping(day, start, end, exclude_id):
            taken_by = other.tuition_class
            when = f"{day:%d %b} {other.start_time:%H:%M}–{other.end_time:%H:%M}"
            if hall_id is not None and other.hall_id == hall_id:
                raise RuleViolation(
                    f"{other.hall.name} is taken by {taken_by.title} on {when}", code="hall_clash"
                )
            if taken_by.teacher_id == cls.teacher_id:
                raise RuleViolation(
                    f"{cls.teacher.name} teaches {taken_by.title} on {when}", code="teacher_clash"
                )

    def _check_hall(self, hall_id: int, branch_id: int) -> None:
        hall = self.halls.get_or_404(hall_id)
        if hall.branch_id != branch_id:
            raise RuleViolation(f"{hall.name} is in another branch")

    def _out(self, sessions: list[ClassSession]) -> list[SessionOut]:
        counts = self.attendance.counts([s.id for s in sessions])
        result = []
        for s in sessions:
            c = counts.get(s.id, {})
            result.append(
                SessionOut.model_validate(s).model_copy(
                    update={
                        "counts": SessionCounts(
                            present=c.get(AttendanceStatus.PRESENT, 0),
                            late=c.get(AttendanceStatus.LATE, 0),
                            absent=c.get(AttendanceStatus.ABSENT, 0),
                        )
                    }
                )
            )
        return result


class AttendanceService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.days = SessionService(db, ctx)
        self.attendance = AttendanceRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.students = StudentRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)
        self.fees = FeeRules(db, ctx)

    def door_status(self, paid: bool, day: dt.date) -> FeeStatus:
        """Unpaid: a warning up to `warning_until_day` (default the 14th), then blocked."""
        if paid:
            return FeeStatus.PAID
        if day.day <= self.fees.settings.warning_until_day:
            return FeeStatus.WARNING
        return FeeStatus.BLOCKED

    # The class list for one day

    def roster(self, session_id: int) -> list[RosterRow]:
        session = self.days.get(session_id)
        enrollments = self._attending(session)
        status = self._fee_statuses(enrollments, session.date)
        marks = self.attendance.for_session(session.id)
        return [
            RosterRow(
                student=StudentRef.model_validate(e.student),
                enrollment_id=e.id,
                card_type=e.card_type,
                fee_status=status[e.id],
                attendance=AttendanceMark.model_validate(marks[e.student_id])
                if e.student_id in marks
                else None,
            )
            for e in enrollments
        ]

    def mark(self, session_id: int, data: MarkAllIn) -> list[RosterRow]:
        """Marks students by hand. Unpaid students past the warning days can't be marked
        present: there is no override."""
        session = self.days.get(session_id)
        if session.status == SessionStatus.CANCELLED:
            raise RuleViolation("This class day is cancelled")
        if session.date > clock.today():
            raise RuleViolation("Attendance can be marked on the day or later")

        enrollments = {e.student_id: e for e in self._attending(session)}
        unknown = [m.student_id for m in data.marks if m.student_id not in enrollments]
        if unknown:
            raise NotFound("Some of these students are not in this class")
        status = self._fee_statuses(list(enrollments.values()), session.date)
        blocked = [
            enrollments[m.student_id].student.name
            for m in data.marks
            if m.status != AttendanceStatus.ABSENT
            and status[enrollments[m.student_id].id] == FeeStatus.BLOCKED
        ]
        if blocked:
            raise RuleViolation(
                f"Fee not paid, so entry is blocked for: {', '.join(blocked)}",
                code="fee_blocked",
            )

        marks = self.attendance.for_session(session.id)
        now = clock.now()
        for m in data.marks:
            e = enrollments[m.student_id]
            row = marks.get(m.student_id)
            if row is None:
                row = self.attendance.add(
                    Attendance(
                        session_id=session.id,
                        student_id=e.student_id,
                        enrollment_id=e.id,
                        status=m.status,
                        method=AttendanceMethod.MANUAL,
                        fee_status=status[e.id],
                        marked_by_id=self.ctx.user.id,
                        marked_at=now,
                    )
                )
            elif row.status != m.status:
                row.status = m.status
                row.method = AttendanceMethod.MANUAL
                row.marked_by_id = self.ctx.user.id
                row.marked_at = now
        self.db.commit()
        return self.roster(session.id)

    # Door scan

    def scan(self, data: ScanIn) -> ScanOut:
        branch = self.branches.get_or_404(data.branch_id)
        student = self._student(data)
        if not student.is_active:
            raise RuleViolation(f"{student.name} is not an active student")
        ref = StudentRef.model_validate(student)

        now = clock.now()
        today = now.date()
        month = month_of(today)
        mine = {
            e.class_id: e
            for e in self.enrollments.search(None, student.id, None)
            if e.branch_id == branch.id and attends_in(e, month)
        }
        days = [
            s
            for s in self.days.list(today, today, branch_id=branch.id)
            if s.tuition_class.id in mine and s.status == SessionStatus.SCHEDULED
        ]
        session = self._pick(days, today, now)
        if session is None:
            return ScanOut(
                outcome="no_class",
                message=f"{student.name} has no class at {branch.name} now",
                student=ref,
            )

        enrollment = mine[session.tuition_class.id]
        paid = enrollment.id in self.fees.paid_for([enrollment], month)
        fee_status = self.door_status(paid, today)
        due = None if paid else month_charge(enrollment, month, self.fees.settings).amount
        result = {
            "student": ref,
            "session": SessionRef.model_validate(session),
            "fee_status": fee_status,
            "amount_due": due,
        }

        existing = self.attendance.get_one(session.id, student.id)
        if existing is not None:
            at = existing.marked_at.astimezone(now.tzinfo)
            return ScanOut(
                outcome="already",
                message=f"{student.name} was marked at {at:%H:%M}",
                attendance_status=existing.status,
                **result,
            )
        if fee_status == FeeStatus.BLOCKED:
            return ScanOut(
                outcome="blocked",
                message=f"{month_name(month)} fee not paid. Entry is blocked until it is paid.",
                **result,
            )

        start = dt.datetime.combine(today, session.start_time, tzinfo=now.tzinfo)
        status = AttendanceStatus.LATE if now > start + LATE_AFTER else AttendanceStatus.PRESENT
        self.attendance.add(
            Attendance(
                session_id=session.id,
                student_id=student.id,
                enrollment_id=enrollment.id,
                status=status,
                method=AttendanceMethod.QR,
                fee_status=fee_status,
                marked_by_id=self.ctx.user.id,
                marked_at=now,
            )
        )
        self.db.commit()
        if fee_status == FeeStatus.WARNING:
            day = self.fees.settings.warning_until_day
            message = f"{month_name(month)} fee not paid. Please pay by the {_ordinal(day)}."
        else:
            message = f"Welcome, {student.name}"
        return ScanOut(outcome="in", message=message, attendance_status=status, **result)

    def history(self, student_id: int, date_from: dt.date, date_to: dt.date) -> list[Attendance]:
        self.students.get_or_404(student_id)
        return self.attendance.for_student(student_id, date_from, date_to)

    def _student(self, data: ScanIn) -> Student:
        if data.qr_token:
            student = self.students.first(Student.qr_token == data.qr_token)
        else:
            student = self.students.first(Student.code == data.student_code.strip().upper())
        if student is None:
            raise NotFound("This card isn't valid. It may have been replaced by a new one.")
        return student

    @staticmethod
    def _pick(days: list[SessionOut], today: dt.date, now: dt.datetime) -> SessionOut | None:
        """The class happening now (or starting within the hour), earliest first."""

        def window(s: SessionOut) -> tuple[dt.datetime, dt.datetime]:
            start = dt.datetime.combine(today, s.start_time, tzinfo=now.tzinfo)
            end = dt.datetime.combine(today, s.end_time, tzinfo=now.tzinfo)
            return start - EARLY_SCAN, end

        current = [s for s in days if window(s)[0] <= now <= window(s)[1]]
        return min(current, key=lambda s: s.start_time) if current else None

    def _attending(self, session: ClassSession) -> list[Enrollment]:
        """Students in the class in that day's month (including ones who left later)."""
        month = month_of(session.date)
        return [
            e for e in self.enrollments.search(session.class_id, None, None) if attends_in(e, month)
        ]

    def _fee_statuses(self, enrollments: list[Enrollment], day: dt.date) -> dict[int, FeeStatus]:
        paid = self.fees.paid_for(enrollments, month_of(day))
        return {e.id: self.door_status(e.id in paid, day) for e in enrollments}


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

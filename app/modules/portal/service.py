from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, RuleViolation
from app.modules.attendance.models import Attendance
from app.modules.attendance.service import AttendanceService
from app.modules.exams.repository import ExamRepository, MarkRepository
from app.modules.exams.service import ExamService, compute_results
from app.modules.payments.models import Payment
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import DuesOut
from app.modules.payments.service import PaymentService
from app.modules.portal.schemas import PortalExamOut, PortalPartOut, PortalTuteOut
from app.modules.students.models import Student
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.students.schemas import StudentProfileOut
from app.modules.students.service import StudentService
from app.modules.tutes.models import Tute
from app.modules.tutes.repository import TuteIssueRepository, TuteRepository
from app.modules.tutes.service import TuteRules, file_of
from app.tenancy.context import TenantContext

# Why a student can't download a tute, said to the student.
NO_ACCESS = {
    "not_in_class": "This tute isn't for your class",
    "class_fee_unpaid": "Pay that month's class fee first",
    "tute_unpaid": "Pay for this tute first",
}


class PortalService:
    """What a signed-in student sees about themselves.

    A student's records can be in any branch, so this reads across branches, and every
    query is limited to the student's own id.
    """

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = replace(ctx, all_branches=True)
        student = StudentRepository(db, self.ctx).first(Student.user_id == ctx.user.id)
        if student is None:
            raise NotFound("This account has no student profile")
        self.student = student

    def me(self) -> StudentProfileOut:
        return StudentService(self.db, self.ctx).profile(self.student.id)

    def dues(self) -> DuesOut:
        return PaymentService(self.db, self.ctx).dues(self.student.id)

    def receipts(self) -> list[Payment]:
        stmt = PaymentRepository(self.db, self.ctx).search(
            None, None, self.student.id, None, None, None, None
        )
        return list(self.db.scalars(stmt.limit(50)).unique())

    def attendance(self, date_from: dt.date, date_to: dt.date) -> list[Attendance]:
        if (date_to - date_from).days > 366:
            raise RuleViolation("Look at up to a year at a time")
        return AttendanceService(self.db, self.ctx).history(self.student.id, date_from, date_to)

    def tutes(self) -> list[PortalTuteOut]:
        rules = TuteRules(self.db, self.ctx)
        given = TuteIssueRepository(self.db, self.ctx).for_student(self.student.id)
        enrollments = EnrollmentRepository(self.db, self.ctx).for_student(self.student.id)
        result = []
        for tute in TuteRepository(self.db, self.ctx).for_classes(
            [e.class_id for e in enrollments]
        ):
            access = rules.for_student(tute, self.student.id)
            if access.reason == "not_in_class":
                continue  # a tute for a month they weren't in the class
            result.append(
                PortalTuteOut(
                    id=tute.id,
                    title=tute.title,
                    number=tute.number,
                    month=tute.month,
                    access_type=tute.access_type,
                    price=tute.price,
                    teacher_name=tute.teacher.name,
                    has_file=tute.has_file,
                    allowed=access.allowed,
                    reason=access.reason,
                    hard_copy_given=tute.id in given,
                )
            )
        return result

    def tute_file(self, tute_id: int) -> tuple[Path, str]:
        """Checked against payments right now, so a voided receipt takes access away."""
        tute: Tute = TuteRepository(self.db, self.ctx).get_or_404(tute_id)
        access = TuteRules(self.db, self.ctx).for_student(tute, self.student.id)
        if not access.allowed:
            raise RuleViolation(NO_ACCESS[access.reason], code=access.reason)
        return file_of(tute)

    def exams(self) -> list[PortalExamOut]:
        enrollments = EnrollmentRepository(self.db, self.ctx).for_student(self.student.id)
        exams = ExamService(self.db, self.ctx)
        marks = MarkRepository(self.db, self.ctx)
        result = []
        for exam in ExamRepository(self.db, self.ctx).published_for(
            [e.class_id for e in enrollments]
        ):
            results = compute_results(exam, exams.sitting(exam), marks.for_exam(exam.id))
            mine = next((r for r in results.rows if r.student.id == self.student.id), None)
            if mine is None:
                continue
            entered = {p.part_id: p for p in mine.parts}
            result.append(
                PortalExamOut(
                    id=exam.id,
                    title=exam.title,
                    date=exam.date,
                    subject=exam.subject.name,
                    max_total=exam.max_total,
                    total=mine.total,
                    percent=mine.percent,
                    absent=mine.absent,
                    rank=mine.rank,
                    class_rank=mine.class_rank,
                    sat=results.sat,
                    parts=[
                        PortalPartOut(
                            name=p.name,
                            max_marks=p.max_marks,
                            marks=entered[p.id].marks if p.id in entered else None,
                            is_absent=entered[p.id].is_absent if p.id in entered else False,
                        )
                        for p in exam.parts
                    ],
                )
            )
        return result

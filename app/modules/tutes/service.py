from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams
from app.core import clock, storage
from app.core.config import settings
from app.core.exceptions import NotFound, RuleViolation
from app.modules.classes.models import TuitionClass
from app.modules.classes.repository import ClassRepository
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.service import FeeRules
from app.modules.students.models import Enrollment, Student
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.students.schemas import StudentRef
from app.modules.teachers.repository import TeacherRepository
from app.modules.tutes.models import Tute, TuteAccess, TuteIssue
from app.modules.tutes.repository import TuteIssueRepository, TuteRepository
from app.modules.tutes.schemas import NoAccess, TuteCreate, TuteStudentOut, TuteUpdate
from app.tenancy.context import TenantContext

REASONS: dict[str, str] = {
    "not_in_class": "isn't in a class this tute is for",
    "class_fee_unpaid": "hasn't paid the class fee for that month",
    "tute_unpaid": "hasn't paid for this tute",
}


@dataclass(frozen=True)
class Access:
    allowed: bool
    reason: NoAccess | None = None


class TuteRules:
    """Who may have a tute, worked out from payments every time:

    - free tute: the class fee for the tute's month is paid (a free card counts as paid);
    - paid tute: that, and the tute's price is paid too.
    """

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.enrollments = EnrollmentRepository(db, ctx)
        self.payments = PaymentRepository(db, ctx)
        self.fees = FeeRules(db, ctx)

    def for_students(self, tute: Tute, student_id: int | None = None) -> dict[int, Access]:
        """Everyone in the tute's classes that month (or just one student)."""
        enrollments = self.enrollments.attending(tute.class_ids, tute.month, student_id)
        paid = self.fees.paid_for(enrollments, tute.month)
        bought = (
            {s for s, _ in self.payments.tutes_bought(tute_id=tute.id)}
            if tute.access_type == TuteAccess.PAID
            else set()
        )
        by_student: dict[int, list[Enrollment]] = defaultdict(list)
        for e in enrollments:
            by_student[e.student_id].append(e)

        result = {}
        for sid, mine in by_student.items():
            if not any(e.id in paid for e in mine):
                result[sid] = Access(False, "class_fee_unpaid")
            elif tute.access_type == TuteAccess.PAID and sid not in bought:
                result[sid] = Access(False, "tute_unpaid")
            else:
                result[sid] = Access(True)
        return result

    def for_student(self, tute: Tute, student_id: int) -> Access:
        return self.for_students(tute, student_id).get(student_id, Access(False, "not_in_class"))


class TuteService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.tutes = TuteRepository(db, ctx)
        self.issues = TuteIssueRepository(db, ctx)
        self.classes = ClassRepository(db, ctx)
        self.teachers = TeacherRepository(db, ctx)
        self.people = StudentRepository(db, ctx)
        self.rules = TuteRules(db, ctx)

    def list(
        self,
        page: PageParams,
        q: str | None,
        month,
        class_id: int | None,
        teacher_id: int | None,
    ) -> Page:
        stmt = self.tutes.search(q, month, class_id, teacher_id)
        items, total = self.tutes.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, tute_id: int) -> Tute:
        return self.tutes.get_or_404(tute_id)

    def create(self, data: TuteCreate) -> Tute:
        classes = self._classes(data.class_ids)
        teacher_id = data.teacher_id or classes[0].teacher_id
        tute = Tute(
            **data.model_dump(exclude={"class_ids", "teacher_id"}),
            teacher=self.teachers.get_or_404(teacher_id),
            classes=classes,
        )
        self.tutes.add(tute)
        self.db.commit()
        return tute

    def update(self, tute_id: int, data: TuteUpdate) -> Tute:
        tute = self.get(tute_id)
        changes = data.changes()
        if "class_ids" in changes:
            tute.classes = self._classes(changes.pop("class_ids"))
        if "teacher_id" in changes:
            tute.teacher = self.teachers.get_or_404(changes.pop("teacher_id"))
        for field, value in changes.items():
            setattr(tute, field, value)
        if tute.access_type == TuteAccess.PAID and not tute.price:
            raise RuleViolation("Paid tutes need a price")
        if tute.access_type == TuteAccess.FREE:
            tute.price = None
        self.db.commit()
        return tute

    # The soft copy

    def upload(self, tute_id: int, data: bytes, filename: str | None) -> Tute:
        """`data` may be cut at the size limit plus one byte, so oversize files are spotted."""
        tute = self.get(tute_id)
        if len(data) > upload_limit():
            raise RuleViolation(f"The file is bigger than {settings.max_upload_mb} MB")
        if not data.startswith(b"%PDF-"):
            raise RuleViolation("Upload a PDF file")
        old = tute.file_path
        tute.file_path = storage.save(f"tutes/{self.ctx.tenant_id}", data, ".pdf")
        tute.file_name = Path(filename or "tute.pdf").name[:255]
        tute.file_size = len(data)
        self.db.commit()
        if old:
            storage.delete(old)
        return tute

    def remove_file(self, tute_id: int) -> Tute:
        tute = self.get(tute_id)
        old, tute.file_path, tute.file_name, tute.file_size = tute.file_path, None, None, None
        self.db.commit()
        if old:
            storage.delete(old)
        return tute

    def file(self, tute_id: int) -> tuple[Path, str]:
        return file_of(self.get(tute_id))

    # Students and hard copies

    def students(self, tute_id: int) -> list[TuteStudentOut]:
        tute = self.get(tute_id)
        access = self.rules.for_students(tute)
        issued = self.issues.for_tute(tute.id)
        people = {s.id: s for s in self.people.find(Student.id.in_(access.keys()))}
        rows = [
            TuteStudentOut(
                student=StudentRef.model_validate(people[sid]),
                allowed=a.allowed,
                reason=a.reason,
                issued_at=issued[sid].issued_at if sid in issued else None,
            )
            for sid, a in access.items()
        ]
        return sorted(rows, key=lambda r: r.student.name)

    def issue(self, tute_id: int, student_id: int) -> TuteStudentOut:
        """Ticks the hard copy as given. Only for students who may have the tute."""
        tute = self.get(tute_id)
        student = self.people.get_or_404(student_id)
        if not tute.has_hard_copy:
            raise RuleViolation("This tute has no hard copy")
        access = self.rules.for_student(tute, student.id)
        if not access.allowed:
            raise RuleViolation(
                f"{student.name} {REASONS[access.reason]}", code=access.reason or "no_access"
            )
        issued = self.issues.for_tute(tute.id).get(student.id)
        if issued is None:
            issued = self.issues.add(
                TuteIssue(
                    tute_id=tute.id,
                    student_id=student.id,
                    issued_by_id=self.ctx.user.id,
                    issued_at=clock.now(),
                )
            )
            self.db.commit()
        return TuteStudentOut(
            student=StudentRef.model_validate(student),
            allowed=True,
            reason=None,
            issued_at=issued.issued_at,
        )

    def unissue(self, tute_id: int, student_id: int) -> None:
        """Takes the tick off (a mistake)."""
        tute = self.get(tute_id)
        issued = self.issues.for_tute(tute.id).get(student_id)
        if issued is None:
            raise NotFound("That hard copy isn't ticked")
        self.issues.delete(issued)
        self.db.commit()

    def _classes(self, ids: list[int]) -> list[TuitionClass]:
        found = self.classes.find(TuitionClass.id.in_(set(ids)))
        if len(found) != len(set(ids)):
            raise NotFound("Some of the classes were not found")
        return found


def upload_limit() -> int:
    return settings.max_upload_mb * 1024 * 1024


def file_of(tute: Tute) -> tuple[Path, str]:
    if not tute.file_path:
        raise NotFound("This tute has no soft copy")
    path = storage.path_of(tute.file_path)
    if not path.exists():
        raise NotFound("The soft copy file is missing")
    return path, tute.file_name or f"{tute.title}.pdf"

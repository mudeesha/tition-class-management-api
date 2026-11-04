from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams, month_of
from app.core.exceptions import NotFound, RuleViolation
from app.modules.classes.models import TuitionClass
from app.modules.classes.repository import ClassRepository
from app.modules.exams.models import Exam, ExamMark, ExamPart
from app.modules.exams.repository import ExamRepository, MarkRepository
from app.modules.exams.schemas import (
    ExamCreate,
    ExamOut,
    ExamUpdate,
    MarkOut,
    MarksIn,
    PartIn,
    ResultRow,
    ResultsOut,
    SheetRow,
)
from app.modules.students.models import Student
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.students.schemas import StudentRef
from app.modules.subjects.repository import SubjectRepository
from app.modules.teachers.repository import TeacherRepository
from app.tenancy.context import TenantContext


def compute_results(exam: Exam, sitting: dict[int, tuple[Student, int]], marks) -> ResultsOut:
    """Totals, percentages and ranks. Ranks are "1, 2, 2, 4": equal totals share a rank.

    `sitting` maps student id → (student, class id). Students with no marks entered at all
    are left out; students absent for every part are listed last without a rank.
    """
    by_student: dict[int, dict[int, ExamMark]] = {}
    for m in marks:
        by_student.setdefault(m.student_id, {})[m.part_id] = m

    rows: list[ResultRow] = []
    for student_id, entered in by_student.items():
        if student_id not in sitting:
            continue
        student, class_id = sitting[student_id]
        absent = all(m.is_absent for m in entered.values())
        total = (
            None if absent else sum((m.marks or Decimal(0) for m in entered.values()), Decimal(0))
        )
        rows.append(
            ResultRow(
                student=StudentRef.model_validate(student),
                class_id=class_id,
                total=total,
                percent=_percent(total, exam.max_total),
                absent=absent,
                rank=None,
                class_rank=None,
                parts=[
                    MarkOut(
                        part_id=p.id, marks=entered[p.id].marks, is_absent=entered[p.id].is_absent
                    )
                    for p in exam.parts
                    if p.id in entered
                ],
            )
        )

    sat = sorted((r for r in rows if not r.absent), key=lambda r: (-r.total, r.student.name))
    _rank(sat, "rank")
    for class_id in {r.class_id for r in sat}:
        _rank([r for r in sat if r.class_id == class_id], "class_rank")
    away = sorted((r for r in rows if r.absent), key=lambda r: r.student.name)

    totals = [r.total for r in sat]
    return ResultsOut(
        exam=ExamOut.model_validate(exam),
        sat=len(sat),
        absent=len(away),
        average=(sum(totals) / len(totals)).quantize(Decimal("0.01")) if totals else None,
        highest=max(totals) if totals else None,
        rows=sat + away,
    )


def _percent(total: Decimal | None, out_of: Decimal) -> Decimal | None:
    if total is None or not out_of:
        return None
    return (total * 100 / out_of).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rank(rows: list[ResultRow], field: str) -> None:
    previous, rank = None, 0
    for i, row in enumerate(rows, start=1):
        if row.total != previous:
            rank, previous = i, row.total
        setattr(row, field, rank)


class ExamService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.exams = ExamRepository(db, ctx)
        self.marks = MarkRepository(db, ctx)
        self.classes = ClassRepository(db, ctx)
        self.subjects = SubjectRepository(db, ctx)
        self.teachers = TeacherRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.students = StudentRepository(db, ctx)

    def list(
        self, page: PageParams, q, class_id, teacher_id, subject_id, date_from, date_to
    ) -> Page:
        stmt = self.exams.search(q, class_id, teacher_id, subject_id, date_from, date_to)
        items, total = self.exams.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, exam_id: int) -> Exam:
        return self.exams.get_or_404(exam_id)

    def create(self, data: ExamCreate) -> Exam:
        classes = self._classes(data.class_ids)
        exam = Exam(
            title=data.title,
            date=data.date,
            subject=self.subjects.get_or_404(data.subject_id or classes[0].subject_id),
            teacher=self.teachers.get_or_404(data.teacher_id or classes[0].teacher_id),
            classes=classes,
            parts=[
                ExamPart(
                    tenant_id=self.ctx.tenant_id, name=p.name, max_marks=p.max_marks, position=i
                )
                for i, p in enumerate(data.parts)
            ],
        )
        self.exams.add(exam)
        self.db.commit()
        return exam

    def update(self, exam_id: int, data: ExamUpdate) -> Exam:
        exam = self.get(exam_id)
        changes = data.changes()
        if "class_ids" in changes:
            exam.classes = self._classes(changes.pop("class_ids"))
        if "parts" in changes:
            changes.pop("parts")
            self._replace_parts(exam, data.parts)
        for field, value in changes.items():
            setattr(exam, field, value)
        self.db.commit()
        return exam

    # Marks

    def sheet(self, exam_id: int) -> list[SheetRow]:
        exam = self.get(exam_id)
        sitting = self.sitting(exam)
        entered: dict[int, list[MarkOut]] = {}
        for m in self.marks.for_exam(exam.id):
            entered.setdefault(m.student_id, []).append(MarkOut.model_validate(m))
        rows = [
            SheetRow(
                student=StudentRef.model_validate(student),
                class_id=class_id,
                marks=entered.get(student.id, []),
            )
            for student, class_id in sitting.values()
        ]
        return sorted(rows, key=lambda r: r.student.name)

    def save_marks(self, exam_id: int, data: MarksIn) -> list[SheetRow]:
        exam = self.get(exam_id)
        sitting = self.sitting(exam)
        parts = {p.id: p for p in exam.parts}
        existing = {(m.student_id, m.part_id): m for m in self.marks.for_exam(exam.id)}

        for line in data.marks:
            if line.student_id not in sitting:
                raise NotFound("Some of these students don't sit this exam")
            part = parts.get(line.part_id)
            if part is None:
                raise NotFound("Some of these parts are not in this exam")
            if not line.is_absent and line.marks is None:
                raise RuleViolation("Give marks or mark the student absent")
            if line.marks is not None and line.marks > part.max_marks:
                name = sitting[line.student_id][0].name
                raise RuleViolation(f"{name}: {part.name} is out of {part.max_marks}")

            row = existing.get((line.student_id, line.part_id))
            if row is None:
                self.marks.add(
                    ExamMark(
                        exam_id=exam.id,
                        part_id=part.id,
                        student_id=line.student_id,
                        marks=line.marks,
                        is_absent=line.is_absent,
                        entered_by_id=self.ctx.user.id,
                    )
                )
            else:
                row.marks, row.is_absent = line.marks, line.is_absent
                row.entered_by_id = self.ctx.user.id
        self.db.commit()
        return self.sheet(exam.id)

    def results(self, exam_id: int) -> ResultsOut:
        exam = self.get(exam_id)
        return compute_results(exam, self.sitting(exam), self.marks.for_exam(exam.id))

    # Helpers

    def sitting(self, exam: Exam) -> dict[int, tuple[Student, int]]:
        """Students in the exam's classes in the exam's month."""
        result: dict[int, tuple[Student, int]] = {}
        for e in self.enrollments.attending(exam.class_ids, month_of(exam.date)):
            result.setdefault(e.student_id, (e.student, e.class_id))
        return result

    def _replace_parts(self, exam: Exam, wanted: list[PartIn]) -> None:
        current = {p.id: p for p in exam.parts}
        unknown = [p.id for p in wanted if p.id is not None and p.id not in current]
        if unknown:
            raise NotFound("Some of these parts are not in this exam")
        keep = {p.id for p in wanted if p.id is not None}
        for part_id, part in current.items():
            if part_id not in keep and self.marks.any_for_part(part_id):
                raise RuleViolation(f"{part.name} already has marks, so it can't be removed")

        parts = []
        for i, p in enumerate(wanted):
            if p.id is None:
                part = ExamPart(tenant_id=self.ctx.tenant_id, name=p.name, max_marks=p.max_marks)
            else:
                part = current[p.id]
                highest = self.marks.highest_for_part(part.id)
                if highest is not None and p.max_marks < highest:
                    raise RuleViolation(f"{p.name} has marks up to {highest} already")
                part.name, part.max_marks = p.name, p.max_marks
            part.position = i
            parts.append(part)
        exam.parts = parts

    def _classes(self, ids: list[int]) -> list[TuitionClass]:
        found = self.classes.find(TuitionClass.id.in_(set(ids)))
        if len(found) != len(set(ids)):
            raise NotFound("Some of the classes were not found")
        return found

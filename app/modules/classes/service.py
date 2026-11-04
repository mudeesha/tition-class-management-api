from __future__ import annotations

from datetime import time

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams
from app.core import clock
from app.core.exceptions import Conflict, RuleViolation
from app.modules.attendance.models import ClassSession
from app.modules.attendance.repository import SessionRepository
from app.modules.branches.models import Branch, Hall
from app.modules.branches.repository import BranchRepository, HallRepository
from app.modules.classes.models import ClassLevel, ClassSchedule, TuitionClass
from app.modules.classes.repository import ClassRepository, ScheduleRepository
from app.modules.classes.schemas import (
    ClassCreate,
    ClassOut,
    ClassUpdate,
    ScheduleCreate,
    ScheduleUpdate,
)
from app.modules.students.repository import EnrollmentRepository
from app.modules.subjects.models import Subject
from app.modules.subjects.repository import SubjectRepository
from app.modules.teachers.models import Teacher
from app.modules.teachers.repository import TeacherRepository
from app.tenancy.context import TenantContext


class ClassService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.classes = ClassRepository(db, ctx)
        self.schedules = ScheduleRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)
        self.halls = HallRepository(db, ctx)
        self.subjects = SubjectRepository(db, ctx)
        self.teachers = TeacherRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.days = SessionRepository(db, ctx)

    # Classes

    def list(
        self,
        page: PageParams,
        q: str | None,
        branch_id: int | None,
        teacher_id: int | None,
        subject_id: int | None,
        level: ClassLevel | None,
        exam_year: int | None,
        is_active: bool | None,
    ) -> Page:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        stmt = self.classes.search(
            q, branch_id, teacher_id, subject_id, level, exam_year, is_active
        )
        items, total = self.classes.paginate(stmt, page.page, page.size)
        return Page(items=self._with_counts(items), total=total, page=page.page, size=page.size)

    def get(self, class_id: int) -> ClassOut:
        return self._with_counts([self.classes.get_or_404(class_id)])[0]

    def create(self, data: ClassCreate) -> ClassOut:
        branch = self._open_branch(data.branch_id)
        cls = TuitionClass(
            **data.model_dump(exclude={"branch_id", "subject_id", "teacher_id", "hall_id"}),
            branch=branch,
            subject=self._subject(data.subject_id),
            teacher=self._teacher_at(data.teacher_id, branch),
            hall=self._hall_in(data.hall_id, branch.id) if data.hall_id is not None else None,
        )
        self.classes.add(cls)
        self.db.commit()
        return self.get(cls.id)

    def update(self, class_id: int, data: ClassUpdate) -> ClassOut:
        cls = self.classes.get_or_404(class_id)
        changes = data.changes()

        level = changes.get("level", cls.level)
        exam_year = changes.get("exam_year", cls.exam_year)
        if level == ClassLevel.AL and exam_year is None:
            raise RuleViolation("A/L classes need an exam year")

        # Clashes only matter while the class is running.
        recheck = ("teacher_id" in changes and changes["teacher_id"] != cls.teacher_id) or (
            changes.get("is_active") is True and not cls.is_active
        )

        # Set related objects, not just their ids, so the class shows the new ones.
        if "teacher_id" in changes:
            cls.teacher = self._teacher_at(changes.pop("teacher_id"), cls.branch)
        if "subject_id" in changes:
            cls.subject = self._subject(changes.pop("subject_id"))
        if "hall_id" in changes:
            hall_id = changes.pop("hall_id")
            cls.hall = self._hall_in(hall_id, cls.branch_id) if hall_id is not None else None
        for field, value in changes.items():
            setattr(cls, field, value)

        if recheck and cls.is_active:
            for s in cls.schedules:
                self._check_clashes(cls, s.weekday, s.start_time, s.end_time, s.hall_id, s.id)
        if not cls.is_active:
            # A closed class has no more class days.
            self.days.drop_unused(
                ClassSession.class_id == cls.id, ClassSession.date >= clock.today()
            )
        self.db.commit()
        return self.get(cls.id)

    # Weekly schedules

    def add_schedule(self, class_id: int, data: ScheduleCreate) -> ClassSchedule:
        cls = self.classes.get_or_404(class_id)
        hall_id = data.hall_id if "hall_id" in data.model_fields_set else cls.hall_id
        hall = self._hall_in(hall_id, cls.branch_id) if hall_id is not None else None
        if cls.is_active:
            self._check_clashes(cls, data.weekday, data.start_time, data.end_time, hall_id)

        schedule = ClassSchedule(
            tuition_class=cls,
            weekday=data.weekday,
            start_time=data.start_time,
            end_time=data.end_time,
            hall=hall,
        )
        self.schedules.add(schedule)
        self.db.commit()
        return schedule

    def update_schedule(self, schedule_id: int, data: ScheduleUpdate) -> ClassSchedule:
        schedule = self.schedules.get_or_404(schedule_id)
        cls = schedule.tuition_class
        changes = data.changes()

        weekday = changes.get("weekday", schedule.weekday)
        start = changes.get("start_time", schedule.start_time)
        end = changes.get("end_time", schedule.end_time)
        if end <= start:
            raise RuleViolation("The end time must be after the start time")
        hall_id = changes.get("hall_id", schedule.hall_id)
        if "hall_id" in changes:
            schedule.hall = self._hall_in(hall_id, cls.branch_id) if hall_id is not None else None
        if cls.is_active:
            self._check_clashes(cls, weekday, start, end, hall_id, schedule.id)

        schedule.weekday, schedule.start_time, schedule.end_time = weekday, start, end
        self._drop_future_days(schedule)
        self.db.commit()
        return schedule

    def delete_schedule(self, schedule_id: int) -> None:
        schedule = self.schedules.get_or_404(schedule_id)
        self._drop_future_days(schedule)
        self.schedules.delete(schedule)
        self.db.commit()

    def _drop_future_days(self, schedule: ClassSchedule) -> None:
        """Future days made from the old time go; they're made again from the new one."""
        self.days.drop_unused(
            ClassSession.schedule_id == schedule.id, ClassSession.date >= clock.today()
        )

    def timetable(
        self, branch_id: int | None, teacher_id: int | None, hall_id: int | None
    ) -> list[ClassSchedule]:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        return self.schedules.timetable(branch_id, teacher_id, hall_id)

    # Checks

    def _check_clashes(
        self,
        cls: TuitionClass,
        weekday: int,
        start: time,
        end: time,
        hall_id: int | None,
        exclude_id: int | None = None,
    ) -> None:
        """A hall holds one class at a time, and so does a teacher (in any branch)."""
        for other in self.schedules.overlapping(weekday, start, end, exclude_id):
            taken_by = other.tuition_class
            details = {"class_id": taken_by.id, "schedule_id": other.id}
            if hall_id is not None and other.hall_id == hall_id:
                raise Conflict(
                    f"{other.hall.name} is taken by {taken_by.title} on {other.when}",
                    code="hall_clash",
                    details=details,
                )
            if taken_by.teacher_id == cls.teacher_id:
                raise Conflict(
                    f"{cls.teacher.name} already teaches {taken_by.title} on {other.when}",
                    code="teacher_clash",
                    details=details,
                )

    def _open_branch(self, branch_id: int) -> Branch:
        branch = self.branches.get_or_404(branch_id)
        if not branch.is_active:
            raise RuleViolation(f"The {branch.name} branch is inactive")
        return branch

    def _subject(self, subject_id: int) -> Subject:
        return self.subjects.get_or_404(subject_id)

    def _teacher_at(self, teacher_id: int, branch: Branch) -> Teacher:
        teacher = self.teachers.get_or_404(teacher_id)
        if not teacher.is_active:
            raise RuleViolation(f"{teacher.name} is inactive")
        if branch.id not in teacher.branch_ids:
            raise RuleViolation(
                f"{teacher.name} isn't assigned to the {branch.name} branch. "
                "Add the branch on the teacher's profile first."
            )
        return teacher

    def _hall_in(self, hall_id: int, branch_id: int) -> Hall:
        hall = self.halls.get_or_404(hall_id)
        if hall.branch_id != branch_id:
            raise RuleViolation(f"{hall.name} is in another branch")
        if not hall.is_active:
            raise RuleViolation(f"{hall.name} is inactive")
        return hall

    def _with_counts(self, classes: list[TuitionClass]) -> list[ClassOut]:
        counts = self.enrollments.active_counts([c.id for c in classes])
        return [
            ClassOut.model_validate(c).model_copy(update={"student_count": counts.get(c.id, 0)})
            for c in classes
        ]

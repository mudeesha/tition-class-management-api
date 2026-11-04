from datetime import time

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import contains_eager

from app.common.repository import BranchScopedRepository, TenantScopedRepository
from app.modules.classes.models import ClassLevel, ClassSchedule, TuitionClass
from app.modules.subjects.models import Subject
from app.modules.teachers.models import Teacher


class ClassRepository(BranchScopedRepository[TuitionClass]):
    model = TuitionClass
    label = "Class"

    def search(
        self,
        q: str | None,
        branch_id: int | None,
        teacher_id: int | None,
        subject_id: int | None,
        level: ClassLevel | None,
        exam_year: int | None,
        is_active: bool | None,
    ) -> Select[tuple[TuitionClass]]:
        stmt = (
            self.query()
            .join(Subject, Subject.id == TuitionClass.subject_id)
            .join(Teacher, Teacher.id == TuitionClass.teacher_id)
        )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(TuitionClass.name).like(like),
                    func.lower(Subject.name).like(like),
                    func.lower(Teacher.name).like(like),
                )
            )
        filters = {
            TuitionClass.branch_id: branch_id,
            TuitionClass.teacher_id: teacher_id,
            TuitionClass.subject_id: subject_id,
            TuitionClass.level: level,
            TuitionClass.exam_year: exam_year,
            TuitionClass.is_active: is_active,
        }
        for column, value in filters.items():
            if value is not None:
                stmt = stmt.where(column == value)
        return stmt.order_by(
            Subject.name,
            TuitionClass.exam_year.nulls_first(),
            TuitionClass.level,
            TuitionClass.name,
        )

    def active_in_tenant(self) -> list[TuitionClass]:
        """Every running class, in every branch (for clash checks)."""
        stmt = select(TuitionClass).where(
            TuitionClass.tenant_id == self.ctx.tenant_id, TuitionClass.is_active.is_(True)
        )
        return list(self.db.scalars(stmt).unique())


class ScheduleRepository(TenantScopedRepository[ClassSchedule]):
    """Schedules are seen through their class, so branch access follows the class."""

    model = ClassSchedule
    label = "Schedule"

    def query(self) -> Select[tuple[ClassSchedule]]:
        stmt = (
            super()
            .query()
            .join(ClassSchedule.tuition_class)
            .options(contains_eager(ClassSchedule.tuition_class))
        )
        if not self.ctx.all_branches:
            stmt = stmt.where(TuitionClass.branch_id.in_(self.ctx.branch_ids))
        return stmt

    def timetable(
        self, branch_id: int | None, teacher_id: int | None, hall_id: int | None
    ) -> list[ClassSchedule]:
        stmt = self.query().where(TuitionClass.is_active.is_(True))
        if branch_id is not None:
            stmt = stmt.where(TuitionClass.branch_id == branch_id)
        if teacher_id is not None:
            stmt = stmt.where(TuitionClass.teacher_id == teacher_id)
        if hall_id is not None:
            stmt = stmt.where(ClassSchedule.hall_id == hall_id)
        return list(self.db.scalars(stmt.order_by(ClassSchedule.weekday, ClassSchedule.start_time)))

    def overlapping(
        self, weekday: int, start: time, end: time, exclude_id: int | None = None
    ) -> list[ClassSchedule]:
        """Slots of active classes that overlap this time, in every branch.

        Not limited to the caller's branches: a teacher can't be in Galle and Kandy at once.
        """
        stmt = (
            select(ClassSchedule)
            .join(ClassSchedule.tuition_class)
            .options(contains_eager(ClassSchedule.tuition_class))
            .where(
                ClassSchedule.tenant_id == self.ctx.tenant_id,
                TuitionClass.is_active.is_(True),
                ClassSchedule.weekday == weekday,
                ClassSchedule.start_time < end,
                ClassSchedule.end_time > start,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(ClassSchedule.id != exclude_id)
        return list(self.db.scalars(stmt))

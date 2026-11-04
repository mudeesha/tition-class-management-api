import datetime as dt
from collections import Counter

from sqlalchemy import ColumnElement, delete, exists, select, text
from sqlalchemy.dialects.postgresql import insert

from app.common.repository import BranchScopedRepository, TenantScopedRepository
from app.modules.attendance.models import (
    Attendance,
    AttendanceStatus,
    ClassSession,
    SessionKind,
    SessionStatus,
)
from app.modules.classes.models import TuitionClass


class SessionRepository(BranchScopedRepository[ClassSession]):
    model = ClassSession
    label = "Class day"

    def between(
        self,
        date_from: dt.date,
        date_to: dt.date,
        class_id: int | None = None,
        branch_id: int | None = None,
    ) -> list[ClassSession]:
        where = [ClassSession.date >= date_from, ClassSession.date <= date_to]
        if class_id is not None:
            where.append(ClassSession.class_id == class_id)
        if branch_id is not None:
            where.append(ClassSession.branch_id == branch_id)
        return self.find(*where, order_by=[ClassSession.date, ClassSession.start_time])

    def create_missing(self, rows: list[dict]) -> None:
        """Adds regular days; ones that already exist (even cancelled) are left alone."""
        if not rows:
            return
        stmt = (
            insert(ClassSession)
            .values(
                [
                    {
                        **row,
                        "tenant_id": self.ctx.tenant_id,
                        "kind": SessionKind.REGULAR.value,
                        "status": SessionStatus.SCHEDULED.value,
                    }
                    for row in rows
                ]
            )
            .on_conflict_do_nothing(
                index_elements=["schedule_id", "date"], index_where=text("schedule_id IS NOT NULL")
            )
        )
        self.db.execute(stmt)

    def overlapping(
        self, day: dt.date, start: dt.time, end: dt.time, exclude_id: int | None = None
    ) -> list[ClassSession]:
        """Days of active classes at an overlapping time, in every branch."""
        stmt = (
            select(ClassSession)
            .join(ClassSession.tuition_class)
            .where(
                ClassSession.tenant_id == self.ctx.tenant_id,
                TuitionClass.is_active.is_(True),
                ClassSession.status == SessionStatus.SCHEDULED,
                ClassSession.date == day,
                ClassSession.start_time < end,
                ClassSession.end_time > start,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(ClassSession.id != exclude_id)
        return list(self.db.scalars(stmt).unique())

    def drop_unused(self, *where: ColumnElement[bool]) -> None:
        """Deletes days nobody has been marked on yet, e.g. after the weekly time changed.

        They are made again (with the new time) the next time someone looks.
        """
        unused = ~exists().where(Attendance.session_id == ClassSession.id)
        stmt = delete(ClassSession).where(
            ClassSession.tenant_id == self.ctx.tenant_id, unused, *where
        )
        self.db.execute(stmt, execution_options={"synchronize_session": False})


class AttendanceRepository(TenantScopedRepository[Attendance]):
    model = Attendance
    label = "Attendance"

    def for_session(self, session_id: int) -> dict[int, Attendance]:
        return {a.student_id: a for a in self.find(Attendance.session_id == session_id)}

    def get_one(self, session_id: int, student_id: int) -> Attendance | None:
        return self.first(Attendance.session_id == session_id, Attendance.student_id == student_id)

    def counts(self, session_ids: list[int]) -> dict[int, Counter]:
        if not session_ids:
            return {}
        stmt = select(Attendance.session_id, Attendance.status).where(
            Attendance.tenant_id == self.ctx.tenant_id, Attendance.session_id.in_(session_ids)
        )
        result: dict[int, Counter] = {}
        for session_id, status in self.db.execute(stmt).all():
            result.setdefault(session_id, Counter())[AttendanceStatus(status)] += 1
        return result

    def for_student(
        self, student_id: int, date_from: dt.date, date_to: dt.date
    ) -> list[Attendance]:
        stmt = (
            self.query()
            .join(Attendance.session)
            .where(
                Attendance.student_id == student_id,
                ClassSession.date >= date_from,
                ClassSession.date <= date_to,
            )
        )
        if not self.ctx.all_branches:
            stmt = stmt.where(ClassSession.branch_id.in_(self.ctx.branch_ids))
        stmt = stmt.order_by(ClassSession.date.desc(), ClassSession.start_time.desc())
        return list(self.db.scalars(stmt).unique())

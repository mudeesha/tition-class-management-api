from datetime import date

from sqlalchemy import Select, exists, func, or_, select

from app.common.repository import BranchScopedRepository, TenantScopedRepository
from app.modules.students.models import Enrollment, EnrollmentStatus, Student

_ACTIVE = EnrollmentStatus.ACTIVE


class StudentRepository(TenantScopedRepository[Student]):
    """Students belong to the whole institute, so every branch can find and enrol them.

    Their enrollments are branch data and use EnrollmentRepository.
    """

    model = Student
    label = "Student"

    def search(
        self,
        q: str | None,
        branch_id: int | None,
        class_id: int | None,
        grade: int | None,
        is_active: bool | None,
    ) -> Select[tuple[Student]]:
        stmt = self.query()
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Student.name).like(like),
                    func.lower(Student.code).like(like),
                    Student.phone.like(like),
                    Student.guardian_phone.like(like),
                )
            )
        if branch_id is not None:
            # Their home branch, or a class they attend there.
            stmt = stmt.where(
                or_(
                    Student.home_branch_id == branch_id,
                    self._attends(Enrollment.branch_id == branch_id),
                )
            )
        if class_id is not None:
            stmt = stmt.where(self._attends(Enrollment.class_id == class_id))
        if grade is not None:
            stmt = stmt.where(Student.grade == grade)
        if is_active is not None:
            stmt = stmt.where(Student.is_active.is_(is_active))
        return stmt.order_by(Student.name, Student.id)

    def count_active(self) -> int:
        return self.count(Student.is_active.is_(True))

    @staticmethod
    def _attends(condition):
        return exists().where(
            Enrollment.student_id == Student.id, Enrollment.status == _ACTIVE, condition
        )


class EnrollmentRepository(BranchScopedRepository[Enrollment]):
    model = Enrollment
    label = "Enrollment"

    def search(
        self,
        class_id: int | None,
        student_id: int | None,
        status: EnrollmentStatus | None,
    ) -> list[Enrollment]:
        stmt = self.query().join(Enrollment.student)
        if class_id is not None:
            stmt = stmt.where(Enrollment.class_id == class_id)
        if student_id is not None:
            stmt = stmt.where(Enrollment.student_id == student_id)
        if status is not None:
            stmt = stmt.where(Enrollment.status == status)
        return list(
            self.db.scalars(stmt.order_by(Student.name, Enrollment.start_month.desc())).unique()
        )

    def for_student(self, student_id: int) -> list[Enrollment]:
        return self.find(
            Enrollment.student_id == student_id,
            order_by=[(Enrollment.status != _ACTIVE), Enrollment.start_month.desc()],
        )

    def active(self, class_id: int, ids: list[int] | None = None) -> list[Enrollment]:
        where = [Enrollment.class_id == class_id, Enrollment.status == _ACTIVE]
        if ids is not None:
            where.append(Enrollment.id.in_(ids))
        return self.find(*where)

    def attending(
        self, class_ids: list[int], month: date, student_id: int | None = None
    ) -> list[Enrollment]:
        """Enrollments in these classes during that month (including people who left later)."""
        if not class_ids:
            return []
        where = [
            Enrollment.class_id.in_(class_ids),
            Enrollment.start_month <= month,
            or_(Enrollment.end_month.is_(None), Enrollment.end_month >= month),
        ]
        if student_id is not None:
            where.append(Enrollment.student_id == student_id)
        return self.find(*where)

    def active_in_class(self, student_id: int, class_id: int) -> Enrollment | None:
        """Checks every branch, since the unique index does too."""
        stmt = select(Enrollment).where(
            Enrollment.tenant_id == self.ctx.tenant_id,
            Enrollment.student_id == student_id,
            Enrollment.class_id == class_id,
            Enrollment.status == _ACTIVE,
        )
        return self.db.scalars(stmt.limit(1)).first()

    def active_counts(self, class_ids: list[int]) -> dict[int, int]:
        if not class_ids:
            return {}
        stmt = (
            select(Enrollment.class_id, func.count())
            .where(
                Enrollment.tenant_id == self.ctx.tenant_id,
                Enrollment.class_id.in_(class_ids),
                Enrollment.status == _ACTIVE,
            )
            .group_by(Enrollment.class_id)
        )
        return dict(self.db.execute(stmt).all())

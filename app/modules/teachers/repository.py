from sqlalchemy import Select, exists, func, or_, select

from app.common.repository import TenantScopedRepository
from app.modules.teachers.models import Teacher, teacher_branches


class TeacherRepository(TenantScopedRepository[Teacher]):
    """A member limited to some branches sees teachers who teach in at least one of them."""

    model = Teacher
    label = "Teacher"

    def query(self) -> Select[tuple[Teacher]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(self._in_branches(self.ctx.branch_ids))
        return stmt

    def search(self, q: str | None, branch_id: int | None, is_active: bool | None):
        stmt = self.query()
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Teacher.name).like(like),
                    Teacher.phone.like(like),
                    func.lower(Teacher.nic).like(like),
                )
            )
        if branch_id is not None:
            stmt = stmt.where(self._in_branches({branch_id}))
        if is_active is not None:
            stmt = stmt.where(Teacher.is_active.is_(is_active))
        return stmt.order_by(Teacher.name)

    def _tenant_query(self) -> Select[tuple[Teacher]]:
        return super().query()

    def count_active_in_tenant(self) -> int:
        stmt = self._tenant_query().where(Teacher.is_active.is_(True))
        return self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def nic_taken_in_tenant(self, nic: str, exclude_id: int | None = None) -> bool:
        stmt = self._tenant_query().where(func.upper(Teacher.nic) == nic.upper())
        if exclude_id is not None:
            stmt = stmt.where(Teacher.id != exclude_id)
        return self.db.scalars(stmt.limit(1)).first() is not None

    def membership_linked(self, membership_id: int, exclude_id: int | None = None) -> bool:
        stmt = self._tenant_query().where(Teacher.membership_id == membership_id)
        if exclude_id is not None:
            stmt = stmt.where(Teacher.id != exclude_id)
        return self.db.scalars(stmt.limit(1)).first() is not None

    @staticmethod
    def _in_branches(branch_ids):
        return exists().where(
            teacher_branches.c.teacher_id == Teacher.id,
            teacher_branches.c.branch_id.in_(branch_ids),
        )

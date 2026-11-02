from sqlalchemy import Select, func, select

from app.common.repository import BranchScopedRepository, TenantScopedRepository
from app.modules.branches.models import Branch, Hall


class BranchRepository(TenantScopedRepository[Branch]):
    """Lists only the branches the current member can work in.

    Uniqueness and plan-limit checks use the `*_in_tenant` methods, which see every branch.
    """

    model = Branch
    label = "Branch"

    def query(self) -> Select[tuple[Branch]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(Branch.id.in_(self.ctx.branch_ids))
        return stmt

    def by_ids(self, ids: set[int]) -> list[Branch]:
        return self.find(Branch.id.in_(ids)) if ids else []

    def _tenant_query(self) -> Select[tuple[Branch]]:
        return super().query()

    def code_taken_in_tenant(self, code: str, exclude_id: int | None = None) -> bool:
        stmt = self._tenant_query().where(Branch.code == code)
        if exclude_id is not None:
            stmt = stmt.where(Branch.id != exclude_id)
        return self.db.scalars(stmt.limit(1)).first() is not None

    def count_active_in_tenant(self) -> int:
        stmt = self._tenant_query().where(Branch.is_active.is_(True))
        return self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


class HallRepository(BranchScopedRepository[Hall]):
    model = Hall
    label = "Hall"

    def name_taken(self, branch_id: int, name: str, exclude_id: int | None = None) -> bool:
        where = [Hall.branch_id == branch_id, func.lower(Hall.name) == name.lower()]
        if exclude_id is not None:
            where.append(Hall.id != exclude_id)
        return self.exists(*where)

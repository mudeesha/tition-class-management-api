from sqlalchemy import Select, func, or_

from app.common.repository import Repository
from app.modules.platform.models import Plan, Tenant, TenantStatus


class PlanRepository(Repository[Plan]):
    model = Plan
    label = "Plan"

    def by_code(self, code: str) -> Plan | None:
        return self.first(Plan.code == code)


class TenantRepository(Repository[Tenant]):
    """Platform-level: sees every institute. Only used by platform admin features."""

    model = Tenant
    label = "Institute"

    def code_taken(self, code: str) -> bool:
        return self.exists(Tenant.code == code)

    def search(self, q: str | None, status: TenantStatus | None) -> Select[tuple[Tenant]]:
        stmt = self.query()
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(Tenant.name).like(like), Tenant.code.like(like)))
        if status is not None:
            stmt = stmt.where(Tenant.status == status)
        return stmt.order_by(Tenant.created_at.desc())

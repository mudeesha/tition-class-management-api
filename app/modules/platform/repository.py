from sqlalchemy import Select, func, or_, select

from app.common.repository import Repository
from app.modules.branches.models import Branch
from app.modules.platform.models import Plan, Tenant, TenantStatus
from app.modules.students.models import Student
from app.modules.teachers.models import Teacher
from app.modules.users.models import Membership, Role
from app.tenancy.permissions import RoleKey


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

    def usage(self, tenant_ids: list[int]) -> dict[int, dict[str, int]]:
        """Active students, teachers, branches and staff accounts per institute."""
        result = {t: {"students": 0, "teachers": 0, "branches": 0, "users": 0} for t in tenant_ids}
        if not tenant_ids:
            return result
        counted = {
            "students": (Student.tenant_id, Student.is_active),
            "teachers": (Teacher.tenant_id, Teacher.is_active),
            "branches": (Branch.tenant_id, Branch.is_active),
        }
        for name, (tenant_col, active_col) in counted.items():
            stmt = (
                select(tenant_col, func.count())
                .where(tenant_col.in_(tenant_ids), active_col.is_(True))
                .group_by(tenant_col)
            )
            for tenant_id, n in self.db.execute(stmt).all():
                result[tenant_id][name] = n
        staff = (
            select(Membership.tenant_id, func.count())
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.tenant_id.in_(tenant_ids),
                Membership.is_active.is_(True),
                or_(Role.key.is_(None), Role.key != RoleKey.STUDENT),
            )
            .group_by(Membership.tenant_id)
        )
        for tenant_id, n in self.db.execute(staff).all():
            result[tenant_id]["users"] = n
        return result

    def summary(self) -> dict:
        by_status = dict(
            self.db.execute(select(Tenant.status, func.count()).group_by(Tenant.status)).all()
        )
        revenue = self.db.scalar(
            select(func.coalesce(func.sum(Plan.monthly_price), 0))
            .join(Tenant, Tenant.plan_id == Plan.id)
            .where(Tenant.status == TenantStatus.ACTIVE)
        )
        students = self.db.scalar(
            select(func.count()).select_from(Student).where(Student.is_active.is_(True))
        )
        return {"by_status": by_status, "monthly_revenue": revenue, "students": students}

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams
from app.core.exceptions import Conflict, RuleViolation
from app.core.security import hash_password
from app.modules.branches.models import Branch
from app.modules.institute.models import InstituteSettings
from app.modules.platform.models import Plan, PlanKind, Tenant, TenantStatus
from app.modules.platform.repository import PlanRepository, TenantRepository
from app.modules.platform.schemas import PlanCreate, PlanUpdate, TenantCreate, TenantUpdate
from app.modules.teachers.models import Teacher
from app.modules.users.models import Membership, Role, User
from app.modules.users.repository import PermissionRepository, UserRepository
from app.tenancy.permissions import DEFAULT_ROLES, RoleKey

# Starting plans for a fresh install. Prices are placeholders: set real ones in platform admin.
DEFAULT_PLANS = [
    PlanCreate(
        code="individual",
        name="Individual teacher",
        kind=PlanKind.INDIVIDUAL,
        monthly_price=Decimal("0"),
        max_branches=1,
        max_teachers=1,
        max_students=300,
        max_users=3,
    ),
    PlanCreate(
        code="institute",
        name="Institute",
        kind=PlanKind.INSTITUTE,
        monthly_price=Decimal("0"),
        max_branches=1,
        max_teachers=25,
        max_students=3000,
        max_users=15,
    ),
    PlanCreate(
        code="multi_branch",
        name="Multi-branch institute",
        kind=PlanKind.INSTITUTE,
        monthly_price=Decimal("0"),
        max_branches=5,
        max_teachers=100,
        max_students=10000,
        max_users=50,
    ),
]


def seed_default_plans(db: Session) -> int:
    """Add the default plans that don't exist yet. Returns how many were added."""
    repo = PlanRepository(db)
    added = 0
    for plan in DEFAULT_PLANS:
        if repo.by_code(plan.code) is None:
            repo.add(Plan(**plan.model_dump()))
            added += 1
    db.commit()
    return added


class PlatformService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.plans = PlanRepository(db)
        self.tenants = TenantRepository(db)
        self.users = UserRepository(db)
        self.permissions = PermissionRepository(db)

    # Plans

    def list_plans(self) -> list[Plan]:
        return self.plans.find(order_by=[Plan.monthly_price, Plan.id])

    def create_plan(self, data: PlanCreate) -> Plan:
        if self.plans.by_code(data.code):
            raise Conflict(f"Plan code {data.code} is already used")
        plan = self.plans.add(Plan(**data.model_dump()))
        self.db.commit()
        return plan

    def update_plan(self, plan_id: int, data: PlanUpdate) -> Plan:
        plan = self.plans.get_or_404(plan_id)
        for field, value in data.changes().items():
            setattr(plan, field, value)
        self.db.commit()
        return plan

    # Institutes

    def list_tenants(self, page: PageParams, q: str | None, status: TenantStatus | None) -> Page:
        items, total = self.tenants.paginate(self.tenants.search(q, status), page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get_tenant(self, tenant_id: int) -> Tenant:
        return self.tenants.get_or_404(tenant_id)

    def create_tenant(self, data: TenantCreate) -> Tenant:
        """Set up a new customer: institute, settings, built-in roles, first branch, owner.

        For an individual teacher, the owner also gets a teacher profile.
        """
        plan = self._active_plan(data.plan_id)
        if self.tenants.code_taken(data.code):
            raise Conflict(f"Institute code {data.code} is already used")

        tenant = self.tenants.add(Tenant(**data.model_dump(exclude={"owner"})))
        self.db.add(InstituteSettings(tenant_id=tenant.id))
        roles = self._create_default_roles(tenant.id)
        branch = Branch(tenant_id=tenant.id, name="Main", code="MAIN", is_default=True)
        self.db.add(branch)

        owner = self.users.get_by_email(data.owner.email)
        if owner is None:
            owner = User(
                name=data.owner.name,
                email=data.owner.email,
                phone=data.owner.phone,
                password_hash=hash_password(data.owner.password),
                must_change_password=True,
            )
            self.db.add(owner)
        membership = Membership(
            tenant_id=tenant.id, user=owner, role=roles[RoleKey.OWNER], all_branches=True
        )
        self.db.add(membership)

        if plan.kind == PlanKind.INDIVIDUAL:
            self.db.add(
                Teacher(
                    tenant_id=tenant.id,
                    membership=membership,
                    name=owner.name,
                    phone=owner.phone,
                    email=owner.email,
                    branches=[branch],
                )
            )

        self.db.commit()
        return tenant

    def update_tenant(self, tenant_id: int, data: TenantUpdate) -> Tenant:
        tenant = self.get_tenant(tenant_id)
        changes = data.changes()
        if "plan_id" in changes and changes["plan_id"] != tenant.plan_id:
            tenant.plan = self._active_plan(changes.pop("plan_id"))
        for field, value in changes.items():
            setattr(tenant, field, value)
        self.db.commit()
        return tenant

    def _active_plan(self, plan_id: int) -> Plan:
        plan = self.plans.get_or_404(plan_id)
        if not plan.is_active:
            raise RuleViolation("This plan is no longer offered")
        return plan

    def _create_default_roles(self, tenant_id: int) -> dict[RoleKey, Role]:
        by_code = {p.code: p for p in self.permissions.all()}
        missing = set().union(*(r.permissions for r in DEFAULT_ROLES)) - by_code.keys()
        if missing:
            raise RuntimeError(
                "Permissions are not in the DB. Run: python -m app.cli sync-permissions"
            )

        roles = {}
        for default in DEFAULT_ROLES:
            role = Role(
                tenant_id=tenant_id,
                name=default.name,
                key=default.key,
                is_system=True,
                permissions=[by_code[c] for c in sorted(default.permissions)],
            )
            self.db.add(role)
            roles[default.key] = role
        return roles

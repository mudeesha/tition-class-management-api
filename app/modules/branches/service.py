from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, RuleViolation
from app.modules.branches.models import Branch, Hall
from app.modules.branches.repository import BranchRepository, HallRepository
from app.modules.branches.schemas import BranchCreate, BranchUpdate, HallCreate, HallUpdate
from app.tenancy.context import TenantContext
from app.tenancy.limits import ensure_within_limit


class BranchService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.branches = BranchRepository(db, ctx)

    def list(self) -> list[Branch]:
        return self.branches.find(order_by=[Branch.is_active.desc(), Branch.name])

    def get(self, branch_id: int) -> Branch:
        return self.branches.get_or_404(branch_id)

    def create(self, data: BranchCreate) -> Branch:
        if not self.ctx.all_branches:
            raise Forbidden("Only members with access to all branches can add a branch")
        ensure_within_limit(
            self.ctx.tenant.plan.max_branches, self.branches.count_active_in_tenant(), "branches"
        )
        if self.branches.code_taken_in_tenant(data.code):
            raise Conflict(f"Branch code {data.code} is already used")
        branch = self.branches.add(Branch(**data.model_dump()))
        self.db.commit()
        return branch

    def update(self, branch_id: int, data: BranchUpdate) -> Branch:
        branch = self.get(branch_id)
        changes = data.changes()

        if "code" in changes and self.branches.code_taken_in_tenant(changes["code"], branch.id):
            raise Conflict(f"Branch code {changes['code']} is already used")
        if (
            changes.get("is_active") is False
            and branch.is_active
            and self.branches.count_active_in_tenant() <= 1
        ):
            raise RuleViolation("You need at least one active branch")
        if changes.get("is_active") is True and not branch.is_active:
            ensure_within_limit(
                self.ctx.tenant.plan.max_branches,
                self.branches.count_active_in_tenant(),
                "active branches",
            )

        for field, value in changes.items():
            setattr(branch, field, value)
        self.db.commit()
        return branch


class HallService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.halls = HallRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)

    def list(self, branch_id: int | None = None) -> list[Hall]:
        where = []
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
            where.append(Hall.branch_id == branch_id)
        return self.halls.find(*where, order_by=[Hall.branch_id, Hall.name])

    def get(self, hall_id: int) -> Hall:
        return self.halls.get_or_404(hall_id)

    def create(self, data: HallCreate) -> Hall:
        branch = self.branches.get_or_404(data.branch_id)
        if not branch.is_active:
            raise RuleViolation("This branch is inactive")
        if self.halls.name_taken(branch.id, data.name):
            raise Conflict(f"{branch.name} already has a hall named {data.name}")
        hall = self.halls.add(Hall(**data.model_dump()))
        self.db.commit()
        return hall

    def update(self, hall_id: int, data: HallUpdate) -> Hall:
        hall = self.get(hall_id)
        changes = data.changes()
        if "name" in changes and self.halls.name_taken(hall.branch_id, changes["name"], hall.id):
            raise Conflict(f"This branch already has a hall named {changes['name']}")
        for field, value in changes.items():
            setattr(hall, field, value)
        self.db.commit()
        return hall

    def delete(self, hall_id: int) -> None:
        self.halls.delete(self.get(hall_id))
        self.db.commit()

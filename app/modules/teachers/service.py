from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams
from app.core.exceptions import Conflict, RuleViolation
from app.modules.teachers.models import Teacher
from app.modules.teachers.repository import TeacherRepository
from app.modules.teachers.schemas import TeacherCreate, TeacherUpdate
from app.modules.users.repository import MembershipRepository
from app.modules.users.service import AccessGrants
from app.tenancy.context import TenantContext
from app.tenancy.limits import ensure_within_limit


class TeacherService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.teachers = TeacherRepository(db, ctx)
        self.members = MembershipRepository(db, ctx)
        self.grants = AccessGrants(db, ctx)

    def list(
        self, page: PageParams, q: str | None, branch_id: int | None, is_active: bool | None
    ) -> Page:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        stmt = self.teachers.search(q, branch_id, is_active)
        items, total = self.teachers.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, teacher_id: int) -> Teacher:
        return self.teachers.get_or_404(teacher_id)

    def create(self, data: TeacherCreate) -> Teacher:
        ensure_within_limit(
            self.ctx.tenant.plan.max_teachers, self.teachers.count_active_in_tenant(), "teachers"
        )
        if not self.ctx.all_branches and not data.branch_ids:
            raise RuleViolation("Pick at least one of your branches for this teacher")
        if data.nic and self.teachers.nic_taken_in_tenant(data.nic):
            raise Conflict("A teacher with this NIC already exists")
        if data.membership_id is not None:
            self._check_membership(data.membership_id)

        teacher = Teacher(
            **data.model_dump(exclude={"branch_ids"}),
            branches=self.grants.branches_for(data.branch_ids),
        )
        self.teachers.add(teacher)
        self.db.commit()
        return teacher

    def update(self, teacher_id: int, data: TeacherUpdate) -> Teacher:
        teacher = self.get(teacher_id)
        changes = data.changes()

        if changes.get("nic") and self.teachers.nic_taken_in_tenant(changes["nic"], teacher.id):
            raise Conflict("A teacher with this NIC already exists")
        if changes.get("membership_id") is not None:
            self._check_membership(changes["membership_id"], teacher.id)
        if changes.get("is_active") is True and not teacher.is_active:
            ensure_within_limit(
                self.ctx.tenant.plan.max_teachers,
                self.teachers.count_active_in_tenant(),
                "active teachers",
            )
        if "branch_ids" in changes:
            teacher.branches = self.grants.branches_for(changes.pop("branch_ids"), teacher.branches)

        for field, value in changes.items():
            setattr(teacher, field, value)
        self.db.commit()
        return teacher

    def _check_membership(self, membership_id: int, teacher_id: int | None = None) -> None:
        self.members.get_or_404(membership_id)
        if self.teachers.membership_linked(membership_id, teacher_id):
            raise Conflict("This member is already linked to another teacher")

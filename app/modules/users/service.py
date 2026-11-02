from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams
from app.core.exceptions import Conflict, Forbidden, NotFound, RuleViolation
from app.core.security import hash_password
from app.modules.branches.models import Branch
from app.modules.branches.repository import BranchRepository
from app.modules.users.models import Membership, Permission, Role, User
from app.modules.users.repository import (
    MembershipRepository,
    PermissionRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.users.schemas import MemberCreate, MemberUpdate, RoleCreate, RoleUpdate
from app.tenancy.context import TenantContext
from app.tenancy.limits import ensure_within_limit
from app.tenancy.permissions import PERMISSIONS, RoleKey


def sync_permissions(db: Session) -> int:
    """Copy the permission list from code to the DB. Returns how many were added."""
    repo = PermissionRepository(db)
    existing = {p.code: p for p in repo.all()}
    added = 0
    for p in PERMISSIONS:
        row = existing.get(p.code)
        if row is None:
            repo.add(Permission(code=p.code, module=p.module, description=p.description))
            added += 1
        else:
            row.module, row.description = p.module, p.description
    db.commit()
    return added


class AccessGrants:
    """Rules for handing out permissions and branches.

    A non-owner can only give permissions and branches they have themselves. When they
    edit someone, whatever that person has outside the editor's reach is kept as it is.
    """

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.ctx = ctx
        self.permissions = PermissionRepository(db)
        self.branches = BranchRepository(db, ctx)

    def permissions_for(
        self, codes: list[str], current: Sequence[Permission] = ()
    ) -> list[Permission]:
        wanted = set(codes)
        found = {p.code: p for p in self.permissions.by_codes(wanted)}
        unknown = wanted - found.keys()
        if unknown:
            raise RuleViolation(f"Unknown permissions: {', '.join(sorted(unknown))}")
        if not self.ctx.is_owner:
            beyond = wanted - self.ctx.permissions
            if beyond:
                raise Forbidden(
                    f"You can't give permissions you don't have: {', '.join(sorted(beyond))}"
                )
            kept = [p for p in current if p.code not in self.ctx.permissions]
            return kept + [p for p in found.values() if p not in kept]
        return list(found.values())

    def branches_for(self, ids: list[int], current: Sequence[Branch] = ()) -> list[Branch]:
        wanted = set(ids)
        found = self.branches.by_ids(wanted)
        if len(found) != len(wanted):
            raise NotFound("Some of the branches were not found")
        if not self.ctx.all_branches:
            kept = [b for b in current if b.id not in self.ctx.branch_ids]
            return kept + [b for b in found if b not in kept]
        return found

    def check_all_branches(self, all_branches: bool) -> None:
        if all_branches and not self.ctx.all_branches:
            raise Forbidden("You can't give access to all branches")


class RoleService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.roles = RoleRepository(db, ctx)
        self.grants = AccessGrants(db, ctx)

    def list(self) -> list[Role]:
        return self.roles.find(order_by=[Role.is_system.desc(), Role.name])

    def all_permissions(self) -> list[Permission]:
        return self.grants.permissions.all()

    def get(self, role_id: int) -> Role:
        return self.roles.get_or_404(role_id)

    def create(self, data: RoleCreate) -> Role:
        if self.roles.name_taken(data.name):
            raise Conflict(f"A role named {data.name} already exists")
        role = Role(name=data.name, permissions=self.grants.permissions_for(data.permission_codes))
        self.roles.add(role)
        self.db.commit()
        return role

    def update(self, role_id: int, data: RoleUpdate) -> Role:
        role = self.get(role_id)
        changes = data.changes()
        if role.is_owner:
            raise RuleViolation("The Owner role always has every permission and can't be changed")
        if "name" in changes and changes["name"] != role.name:
            if role.is_system:
                raise RuleViolation("Built-in roles can't be renamed")
            if self.roles.name_taken(changes["name"], role.id):
                raise Conflict(f"A role named {changes['name']} already exists")
            role.name = changes["name"]
        if "permission_codes" in changes:
            role.permissions = self.grants.permissions_for(
                changes["permission_codes"], role.permissions
            )
        self.db.commit()
        return role

    def delete(self, role_id: int) -> None:
        role = self.get(role_id)
        if role.is_system:
            raise RuleViolation("Built-in roles can't be deleted")
        if self.roles.member_counts().get(role.id):
            raise Conflict("Move the members in this role to another role first")
        self.roles.delete(role)
        self.db.commit()


class MemberService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.users = UserRepository(db)
        self.members = MembershipRepository(db, ctx)
        self.roles = RoleRepository(db, ctx)
        self.grants = AccessGrants(db, ctx)

    def list(
        self, page: PageParams, q: str | None, role_id: int | None, is_active: bool | None
    ) -> Page:
        stmt = self.members.search(q, role_id, is_active)
        items, total = self.members.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, member_id: int) -> Membership:
        member = self.members.get_or_404(member_id)
        if member.role.key == RoleKey.STUDENT:
            raise NotFound("Member not found")
        return member

    def create(self, data: MemberCreate) -> Membership:
        role = self._assignable_role(data.role_id)
        self.grants.check_all_branches(data.all_branches)
        branches = self.grants.branches_for(data.branch_ids)
        permissions = self.grants.permissions_for(data.permission_codes)
        ensure_within_limit(self.ctx.tenant.plan.max_users, self.members.count_staff(), "users")

        user = self._find_user(data)
        if user is None:
            if not data.password:
                raise RuleViolation("Set a first password for the new user")
            user = self.users.add(
                User(
                    name=data.name,
                    email=data.email,
                    username=data.username,
                    phone=data.phone,
                    password_hash=hash_password(data.password),
                    must_change_password=True,
                )
            )
        elif self.members.for_user(user.id) is not None:
            raise Conflict("This person is already a member of the institute")

        member = self.members.add(
            Membership(
                user=user,
                role=role,
                all_branches=data.all_branches,
                branches=branches,
                permissions=permissions,
            )
        )
        self.db.commit()
        return member

    def update(self, member_id: int, data: MemberUpdate) -> Membership:
        member = self.get(member_id)
        changes = data.changes()
        is_self = member.id == self.ctx.membership.id

        if member.role.is_owner and not self.ctx.is_owner:
            raise Forbidden("Only an owner can change an owner's access")
        if is_self and ("role_id" in changes or changes.get("is_active") is False):
            raise RuleViolation("You can't change your own role or deactivate yourself")

        if "role_id" in changes and changes["role_id"] != member.role_id:
            new_role = self._assignable_role(changes["role_id"])
            if member.role.is_owner:
                self._keep_an_owner()
            member.role = new_role
        if "all_branches" in changes:
            self.grants.check_all_branches(changes["all_branches"])
            member.all_branches = changes["all_branches"]
        if "branch_ids" in changes:
            member.branches = self.grants.branches_for(changes["branch_ids"], member.branches)
        if "permission_codes" in changes:
            member.permissions = self.grants.permissions_for(
                changes["permission_codes"], member.permissions
            )
        if "is_active" in changes and changes["is_active"] != member.is_active:
            if changes["is_active"]:
                ensure_within_limit(
                    self.ctx.tenant.plan.max_users, self.members.count_staff(), "users"
                )
            elif member.role.is_owner:
                self._keep_an_owner()
            member.is_active = changes["is_active"]

        self.db.commit()
        return member

    def _assignable_role(self, role_id: int) -> Role:
        role = self.roles.get_or_404(role_id)
        if role.key == RoleKey.STUDENT:
            raise RuleViolation("Students are added from the Students section")
        if role.is_owner and not self.ctx.is_owner:
            raise Forbidden("Only an owner can make someone an owner")
        if not self.ctx.is_owner and not set(role.permission_codes) <= self.ctx.permissions:
            raise Forbidden("You can't give a role that has permissions you don't have")
        return role

    def _keep_an_owner(self) -> None:
        if self.members.count_active_owners() <= 1:
            raise RuleViolation("The institute must keep at least one active owner")

    def _find_user(self, data: MemberCreate) -> User | None:
        by_email = self.users.get_by_email(data.email) if data.email else None
        by_username = self.users.get_by_username(data.username) if data.username else None
        if by_email and by_username and by_email.id != by_username.id:
            raise Conflict("The email and username belong to two different users")
        return by_email or by_username

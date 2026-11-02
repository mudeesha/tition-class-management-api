from sqlalchemy import func, or_, select

from app.common.repository import Repository, TenantScopedRepository
from app.modules.users.models import Membership, Permission, Role, User
from app.tenancy.permissions import RoleKey


class UserRepository(Repository[User]):
    model = User
    label = "User"

    def get_by_login(self, login: str) -> User | None:
        login = login.strip().lower()
        return self.first(or_(User.email == login, User.username == login))

    def get_by_email(self, email: str) -> User | None:
        return self.first(User.email == email.lower())

    def get_by_username(self, username: str) -> User | None:
        return self.first(User.username == username.lower())

    def active_memberships(self, user_id: int) -> list[Membership]:
        stmt = (
            select(Membership)
            .where(Membership.user_id == user_id, Membership.is_active.is_(True))
            .order_by(Membership.id)
        )
        return list(self.db.scalars(stmt).unique())

    def active_membership(self, user_id: int, tenant_id: int) -> Membership | None:
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
        )
        return self.db.scalars(stmt).unique().first()


class PermissionRepository(Repository[Permission]):
    model = Permission

    def all(self) -> list[Permission]:
        return self.find(order_by=[Permission.module, Permission.code])

    def by_codes(self, codes: set[str]) -> list[Permission]:
        if not codes:
            return []
        return self.find(Permission.code.in_(codes))


class RoleRepository(TenantScopedRepository[Role]):
    model = Role
    label = "Role"

    def by_key(self, key: RoleKey) -> Role | None:
        return self.first(Role.key == key)

    def name_taken(self, name: str, exclude_id: int | None = None) -> bool:
        where = [func.lower(Role.name) == name.lower()]
        if exclude_id is not None:
            where.append(Role.id != exclude_id)
        return self.exists(*where)

    def member_counts(self) -> dict[int, int]:
        stmt = (
            select(Membership.role_id, func.count())
            .where(Membership.tenant_id == self.ctx.tenant_id)
            .group_by(Membership.role_id)
        )
        return dict(self.db.execute(stmt).all())


class MembershipRepository(TenantScopedRepository[Membership]):
    model = Membership
    label = "Member"

    def for_user(self, user_id: int) -> Membership | None:
        return self.first(Membership.user_id == user_id)

    def search(self, q: str | None, role_id: int | None, is_active: bool | None):
        stmt = self.query().join(Membership.user).join(Membership.role)
        # Students are managed in the students module, not as staff.
        stmt = stmt.where(or_(Role.key.is_(None), Role.key != RoleKey.STUDENT))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.name).like(like),
                    User.email.like(like),
                    User.phone.like(like),
                )
            )
        if role_id is not None:
            stmt = stmt.where(Membership.role_id == role_id)
        if is_active is not None:
            stmt = stmt.where(Membership.is_active.is_(is_active))
        return stmt.order_by(User.name)

    def count_staff(self) -> int:
        """Active non-student members, which is what the plan's max_users limits."""
        stmt = (
            select(func.count())
            .select_from(Membership)
            .join(Membership.role)
            .where(
                Membership.tenant_id == self.ctx.tenant_id,
                Membership.is_active.is_(True),
                or_(Role.key.is_(None), Role.key != RoleKey.STUDENT),
            )
        )
        return self.db.scalar(stmt) or 0

    def count_active_owners(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Membership)
            .join(Membership.role)
            .where(
                Membership.tenant_id == self.ctx.tenant_id,
                Membership.is_active.is_(True),
                Role.key == RoleKey.OWNER,
            )
        )
        return self.db.scalar(stmt) or 0

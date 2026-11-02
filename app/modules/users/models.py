from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum
from app.tenancy.permissions import RoleKey

if TYPE_CHECKING:
    from app.modules.branches.models import Branch
    from app.modules.platform.models import Tenant

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# Extra permissions given directly to one person, on top of their role.
membership_permissions = Table(
    "membership_permissions",
    Base.metadata,
    Column("membership_id", ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# Branches a member can work in. Ignored when membership.all_branches is true.
membership_branches = Table(
    "membership_branches",
    Base.metadata,
    Column("membership_id", ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
)


class User(IdMixin, TimestampMixin, Base):
    """A login. One user can belong to several institutes through memberships."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR username IS NOT NULL", name="has_login"),
    )

    name: Mapped[str] = mapped_column(String(150))
    # Stored lowercase. Students sign in with a username (their student code), staff with email.
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    username: Mapped[str | None] = mapped_column(String(50), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_platform_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Bumped on password change; tokens carrying an older version stop working.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_login_at: Mapped[datetime | None]

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Permission(IdMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    module: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))


class Role(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(100))
    key: Mapped[RoleKey | None] = mapped_column(str_enum(RoleKey))
    is_system: Mapped[bool] = mapped_column(default=False, server_default=false())

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin", order_by=Permission.code
    )

    @property
    def is_owner(self) -> bool:
        return self.key == RoleKey.OWNER

    @property
    def permission_codes(self) -> list[str]:
        return [p.code for p in self.permissions]


class Membership(IdMixin, TenantMixin, TimestampMixin, Base):
    """A user's account inside one institute."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    all_branches: Mapped[bool] = mapped_column(default=False, server_default=false())

    user: Mapped[User] = relationship(back_populates="memberships", lazy="joined")
    tenant: Mapped[Tenant] = relationship(lazy="joined")
    role: Mapped[Role] = relationship(lazy="joined")
    branches: Mapped[list[Branch]] = relationship(secondary=membership_branches, lazy="selectin")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=membership_permissions, lazy="selectin", order_by=Permission.code
    )

    @property
    def branch_ids(self) -> list[int]:
        return sorted(b.id for b in self.branches)

    @property
    def permission_codes(self) -> list[str]:
        return [p.code for p in self.permissions]

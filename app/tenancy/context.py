"""Who is calling, in which institute, and what they may do.

Every tenant endpoint depends on get_tenant_context. The client picks the institute with
the X-Tenant-ID header; the user must have an active membership there.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import DbSession
from app.core.exceptions import AuthenticationFailed, Forbidden, RuleViolation
from app.core.security import TokenType, decode_token
from app.modules.platform.models import Tenant, TenantStatus
from app.modules.users.models import Membership, User
from app.modules.users.repository import UserRepository

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantContext:
    user: User
    tenant: Tenant
    membership: Membership
    is_owner: bool
    permissions: frozenset[str]
    all_branches: bool
    branch_ids: frozenset[int]

    @property
    def tenant_id(self) -> int:
        return self.tenant.id

    def has(self, code: str) -> bool:
        return self.is_owner or code in self.permissions

    def can_access_branch(self, branch_id: int) -> bool:
        return self.all_branches or branch_id in self.branch_ids

    def require_branch(self, branch_id: int) -> None:
        if not self.can_access_branch(branch_id):
            raise Forbidden("You don't have access to this branch")


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationFailed()
    user_id, token_version = decode_token(credentials.credentials, TokenType.ACCESS)
    user = UserRepository(db).get(user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise AuthenticationFailed("Session expired, please sign in again")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def build_context(membership: Membership) -> TenantContext:
    role = membership.role
    is_owner = role.is_owner
    return TenantContext(
        user=membership.user,
        tenant=membership.tenant,
        membership=membership,
        is_owner=is_owner,
        permissions=frozenset(role.permission_codes) | frozenset(membership.permission_codes),
        all_branches=is_owner or membership.all_branches,
        branch_ids=frozenset(membership.branch_ids),
    )


def get_tenant_context(
    db: DbSession,
    user: CurrentUser,
    x_tenant_id: Annotated[int | None, Header()] = None,
) -> TenantContext:
    if x_tenant_id is None:
        raise RuleViolation(
            "Choose an institute first (X-Tenant-ID header)", code="tenant_required"
        )
    if user.must_change_password:
        raise Forbidden("Change your password to continue", code="password_change_required")

    membership = UserRepository(db).active_membership(user.id, x_tenant_id)
    if membership is None:
        raise Forbidden("You are not a member of this institute")
    if membership.tenant.status == TenantStatus.SUSPENDED:
        raise Forbidden("This institute's account is suspended", code="tenant_suspended")
    return build_context(membership)


CurrentContext = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(code: str):
    def check(ctx: CurrentContext) -> TenantContext:
        if not ctx.has(code):
            raise Forbidden(f"You need the '{code}' permission", code="permission_denied")
        return ctx

    return check


def requires(code: str):
    """Use in a route's dependencies list: `dependencies=[requires("branches.manage")]`."""
    return Depends(require_permission(code))


def get_platform_admin(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        raise Forbidden("Platform admins only")
    return user


PlatformAdmin = Annotated[User, Depends(get_platform_admin)]

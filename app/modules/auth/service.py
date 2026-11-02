from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationFailed, RuleViolation
from app.core.security import TokenType, create_token, decode_token, hash_password, verify_password
from app.modules.auth.schemas import (
    ChangePasswordIn,
    ContextOut,
    LoginIn,
    MeMembershipOut,
    MeOut,
    MeUserOut,
    TokenOut,
)
from app.modules.branches.models import Branch
from app.modules.branches.repository import BranchRepository
from app.modules.branches.schemas import BranchRef
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import RoleRef
from app.tenancy.context import TenantContext
from app.tenancy.permissions import PERMISSION_CODES


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def login(self, data: LoginIn) -> TokenOut:
        user = self.users.get_by_login(data.login)
        valid = verify_password(data.password, user.password_hash if user else None)
        if not valid or user is None or not user.is_active:
            raise AuthenticationFailed("Wrong login or password")
        user.last_login_at = datetime.now(UTC)
        self.db.commit()
        return self._tokens(user)

    def refresh(self, refresh_token: str) -> TokenOut:
        user_id, token_version = decode_token(refresh_token, TokenType.REFRESH)
        user = self.users.get(user_id)
        if user is None or not user.is_active or user.token_version != token_version:
            raise AuthenticationFailed("Session expired, please sign in again")
        return self._tokens(user)

    def change_password(self, user: User, data: ChangePasswordIn) -> TokenOut:
        """Also signs the user out everywhere else: old tokens stop working."""
        if not verify_password(data.current_password, user.password_hash):
            raise RuleViolation("Your current password is wrong", code="wrong_password")
        user.password_hash = hash_password(data.new_password)
        user.must_change_password = False
        user.token_version += 1
        self.db.commit()
        return self._tokens(user)

    def me(self, user: User) -> MeOut:
        memberships = [
            MeMembershipOut(
                tenant_id=m.tenant.id,
                tenant_code=m.tenant.code,
                tenant_name=m.tenant.name,
                tenant_status=m.tenant.status,
                plan_kind=m.tenant.plan.kind,
                role=RoleRef.model_validate(m.role),
            )
            for m in self.users.active_memberships(user.id)
        ]
        return MeOut(user=MeUserOut.model_validate(user), memberships=memberships)

    def context(self, ctx: TenantContext) -> ContextOut:
        branches = BranchRepository(self.db, ctx).find(
            Branch.is_active.is_(True), order_by=[Branch.name]
        )
        return ContextOut(
            tenant_id=ctx.tenant.id,
            tenant_code=ctx.tenant.code,
            tenant_name=ctx.tenant.name,
            plan_kind=ctx.tenant.plan.kind,
            role=RoleRef.model_validate(ctx.membership.role),
            is_owner=ctx.is_owner,
            all_branches=ctx.all_branches,
            permissions=sorted(PERMISSION_CODES if ctx.is_owner else ctx.permissions),
            branches=[BranchRef.model_validate(b) for b in branches],
        )

    def _tokens(self, user: User) -> TokenOut:
        return TokenOut(
            access_token=create_token(user.id, user.token_version, TokenType.ACCESS),
            refresh_token=create_token(user.id, user.token_version, TokenType.REFRESH),
            expires_in=settings.access_token_minutes * 60,
            must_change_password=user.must_change_password,
        )

from pydantic import Field, model_validator

from app.common.schemas import Schema
from app.modules.branches.schemas import BranchRef
from app.modules.platform.models import PlanKind, TenantStatus
from app.modules.users.schemas import RoleRef


class LoginIn(Schema):
    login: str = Field(min_length=1, max_length=255, description="Email or username")
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(Schema):
    refresh_token: str


class ChangePasswordIn(Schema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _different(self):
        if self.current_password == self.new_password:
            raise ValueError("The new password must be different")
        return self


class TokenOut(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires
    must_change_password: bool


class MeUserOut(Schema):
    id: int
    name: str
    email: str | None
    username: str | None
    phone: str | None
    is_platform_admin: bool
    must_change_password: bool


class MeMembershipOut(Schema):
    tenant_id: int
    tenant_code: str
    tenant_name: str
    tenant_status: TenantStatus
    plan_kind: PlanKind
    role: RoleRef


class MeOut(Schema):
    user: MeUserOut
    memberships: list[MeMembershipOut]


class ContextOut(Schema):
    """What the signed-in user can do in the chosen institute. The UI builds its menu from this."""

    tenant_id: int
    tenant_code: str
    tenant_name: str
    plan_kind: PlanKind
    role: RoleRef
    is_owner: bool
    all_branches: bool
    permissions: list[str]
    branches: list[BranchRef]

from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.common.schemas import Schema, UpdateSchema
from app.tenancy.permissions import RoleKey

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,50}$"


class PermissionOut(Schema):
    code: str
    module: str
    description: str


class RoleCreate(Schema):
    name: str = Field(min_length=1, max_length=100)
    permission_codes: list[str] = []


class RoleUpdate(UpdateSchema):
    not_null = ("name", "permission_codes")

    name: str | None = Field(None, min_length=1, max_length=100)
    permission_codes: list[str] | None = None


class RoleOut(Schema):
    id: int
    name: str
    key: RoleKey | None
    is_system: bool
    is_owner: bool
    # Empty for the owner role, which always has every permission.
    permission_codes: list[str]


class RoleRef(Schema):
    id: int
    name: str
    key: RoleKey | None


class MemberCreate(Schema):
    """Adds a staff account. If a user with this email/username already exists
    (for example, they work at another institute too), they are added as they are
    and `password` is ignored."""

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    username: str | None = Field(None, pattern=USERNAME_PATTERN)
    phone: str | None = Field(None, max_length=30)
    password: str | None = Field(None, min_length=8, max_length=128)
    role_id: int
    all_branches: bool = False
    branch_ids: list[int] = []
    permission_codes: list[str] = []

    @field_validator("email", "username")
    @classmethod
    def _lower(cls, v: str | None) -> str | None:
        return v.lower() if v else v

    @model_validator(mode="after")
    def _needs_login(self):
        if not self.email and not self.username:
            raise ValueError("Give an email or a username")
        return self


class MemberUpdate(UpdateSchema):
    not_null = ("role_id", "all_branches", "branch_ids", "permission_codes", "is_active")

    role_id: int | None = None
    all_branches: bool | None = None
    branch_ids: list[int] | None = None
    permission_codes: list[str] | None = None
    is_active: bool | None = None


class MemberUserOut(Schema):
    id: int
    name: str
    email: str | None
    username: str | None
    phone: str | None


class MemberOut(Schema):
    id: int
    user: MemberUserOut
    role: RoleRef
    is_active: bool
    all_branches: bool
    branch_ids: list[int]
    # Extra permissions given directly, on top of the role.
    permission_codes: list[str]
    created_at: datetime

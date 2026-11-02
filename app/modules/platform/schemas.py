from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.common.schemas import Money, Schema, UpdateSchema
from app.modules.platform.models import PlanKind, TenantStatus

TENANT_CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$"


class PlanCreate(Schema):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    kind: PlanKind
    monthly_price: Money
    max_branches: int | None = Field(None, ge=1)
    max_teachers: int | None = Field(None, ge=1)
    max_students: int | None = Field(None, ge=1)
    max_users: int | None = Field(None, ge=1)
    is_active: bool = True


class PlanUpdate(UpdateSchema):
    not_null = ("name", "kind", "monthly_price", "is_active")

    name: str | None = Field(None, min_length=1, max_length=100)
    kind: PlanKind | None = None
    monthly_price: Money | None = None
    max_branches: int | None = Field(None, ge=1)
    max_teachers: int | None = Field(None, ge=1)
    max_students: int | None = Field(None, ge=1)
    max_users: int | None = Field(None, ge=1)
    is_active: bool | None = None


class PlanOut(Schema):
    id: int
    code: str
    name: str
    kind: PlanKind
    monthly_price: Money
    max_branches: int | None
    max_teachers: int | None
    max_students: int | None
    max_users: int | None
    is_active: bool


class OwnerIn(Schema):
    """The institute's first owner. An existing user with this email is reused as is."""

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(None, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class TenantCreate(Schema):
    code: str = Field(pattern=TENANT_CODE_PATTERN, description="Short unique name, e.g. saya")
    name: str = Field(min_length=1, max_length=150)
    plan_id: int
    status: TenantStatus = TenantStatus.TRIAL
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)
    owner: OwnerIn

    @field_validator("code")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class TenantUpdate(UpdateSchema):
    not_null = ("name", "plan_id", "status")

    name: str | None = Field(None, min_length=1, max_length=150)
    plan_id: int | None = None
    status: TenantStatus | None = None
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)


class TenantOut(Schema):
    id: int
    code: str
    name: str
    status: TenantStatus
    email: str | None
    phone: str | None
    address: str | None
    plan: PlanOut
    created_at: datetime

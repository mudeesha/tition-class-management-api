from pydantic import EmailStr, Field

from app.common.schemas import Money, Percent, Schema, UpdateSchema
from app.modules.institute.models import DiscountStacking
from app.modules.platform.models import PlanKind, TenantStatus


class PlanLimitsOut(Schema):
    code: str
    name: str
    kind: PlanKind
    max_branches: int | None
    max_teachers: int | None
    max_students: int | None
    max_users: int | None


class InstituteOut(Schema):
    id: int
    code: str
    name: str
    status: TenantStatus
    email: str | None
    phone: str | None
    address: str | None
    plan: PlanLimitsOut


class InstituteUpdate(UpdateSchema):
    not_null = ("name",)

    name: str | None = Field(None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=255)


class SettingsOut(Schema):
    admission_fee: Money
    late_join_from_day: int
    late_join_discount_percent: Percent
    warning_until_day: int
    discount_stacking: DiscountStacking
    tute_institute_share_percent: Percent


class SettingsUpdate(UpdateSchema):
    not_null = (
        "admission_fee",
        "late_join_from_day",
        "late_join_discount_percent",
        "warning_until_day",
        "discount_stacking",
        "tute_institute_share_percent",
    )

    admission_fee: Money | None = None
    late_join_from_day: int | None = Field(
        None, ge=2, le=31, description="First day of the month that counts as a late join"
    )
    late_join_discount_percent: Percent | None = None
    warning_until_day: int | None = Field(
        None, ge=0, le=31, description="Unpaid students get a warning up to this day, then a block"
    )
    discount_stacking: DiscountStacking | None = None
    tute_institute_share_percent: Percent | None = None

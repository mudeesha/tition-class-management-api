from decimal import Decimal

from pydantic import EmailStr, Field

from app.common.schemas import Percent, Schema, UpdateSchema
from app.modules.branches.schemas import BranchRef


class TeacherCreate(Schema):
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(None, max_length=30)
    email: EmailStr | None = None
    nic: str | None = Field(None, max_length=20)
    institute_share_percent: Percent = Field(
        Decimal("0.00"),
        description="Institute's cut of this teacher's class fees. 0 = teacher keeps it all",
    )
    branch_ids: list[int] = []
    membership_id: int | None = Field(
        None, description="Link to a member account so the teacher can sign in"
    )


class TeacherUpdate(UpdateSchema):
    not_null = ("name", "institute_share_percent", "branch_ids", "is_active")

    name: str | None = Field(None, min_length=1, max_length=150)
    phone: str | None = Field(None, max_length=30)
    email: EmailStr | None = None
    nic: str | None = Field(None, max_length=20)
    institute_share_percent: Percent | None = None
    branch_ids: list[int] | None = None
    membership_id: int | None = None
    is_active: bool | None = None


class TeacherOut(Schema):
    id: int
    name: str
    phone: str | None
    email: str | None
    nic: str | None
    institute_share_percent: Percent
    is_active: bool
    branches: list[BranchRef]
    membership_id: int | None

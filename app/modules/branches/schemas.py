from pydantic import Field, field_validator

from app.common.schemas import Schema, UpdateSchema

CODE_PATTERN = r"^[A-Za-z0-9]+$"


class BranchCreate(Schema):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=10, pattern=CODE_PATTERN)
    city: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=30)

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class BranchUpdate(UpdateSchema):
    not_null = ("name", "code", "is_active")

    name: str | None = Field(None, min_length=1, max_length=100)
    code: str | None = Field(None, min_length=1, max_length=10, pattern=CODE_PATTERN)
    city: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=30)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class BranchOut(Schema):
    id: int
    name: str
    code: str
    city: str | None
    address: str | None
    phone: str | None
    is_active: bool
    is_default: bool


class BranchRef(Schema):
    id: int
    name: str
    code: str


class HallCreate(Schema):
    branch_id: int
    name: str = Field(min_length=1, max_length=100)
    capacity: int | None = Field(None, ge=1, le=10000)


class HallUpdate(UpdateSchema):
    not_null = ("name", "is_active")

    name: str | None = Field(None, min_length=1, max_length=100)
    capacity: int | None = Field(None, ge=1, le=10000)
    is_active: bool | None = None


class HallOut(Schema):
    id: int
    branch: BranchRef
    name: str
    capacity: int | None
    is_active: bool

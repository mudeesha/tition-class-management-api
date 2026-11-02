from pydantic import Field

from app.common.schemas import Schema, UpdateSchema
from app.modules.subjects.models import SubjectLevel


class SubjectCreate(Schema):
    name: str = Field(min_length=1, max_length=100)
    level: SubjectLevel | None = None


class SubjectUpdate(UpdateSchema):
    not_null = ("name",)

    name: str | None = Field(None, min_length=1, max_length=100)
    level: SubjectLevel | None = None


class SubjectOut(Schema):
    id: int
    name: str
    level: SubjectLevel | None

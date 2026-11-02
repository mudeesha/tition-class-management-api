from enum import StrEnum

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin, str_enum


class SubjectLevel(StrEnum):
    PRIMARY = "primary"  # up to grade 5
    OL = "ol"  # grades 6–11, O/L syllabus
    AL = "al"  # grades 12–13, A/L syllabus
    OTHER = "other"


class Subject(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "level", postgresql_nulls_not_distinct=True),
    )

    name: Mapped[str] = mapped_column(String(100))
    level: Mapped[SubjectLevel | None] = mapped_column(str_enum(SubjectLevel))

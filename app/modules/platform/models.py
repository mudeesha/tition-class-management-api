from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TimestampMixin, str_enum


class PlanKind(StrEnum):
    INDIVIDUAL = "individual"  # one teacher, one hidden branch
    # Many teachers. A multi-branch institute is an institute plan with max_branches > 1.
    INSTITUTE = "institute"


class TenantStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Plan(IdMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[PlanKind] = mapped_column(str_enum(PlanKind))
    monthly_price: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    # None means unlimited.
    max_branches: Mapped[int | None]
    max_teachers: Mapped[int | None]
    max_students: Mapped[int | None]
    max_users: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Tenant(IdMixin, TimestampMixin, Base):
    """An institute or an individual teacher: one customer of the platform."""

    __tablename__ = "tenants"

    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[TenantStatus] = mapped_column(str_enum(TenantStatus), default=TenantStatus.TRIAL)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))

    plan: Mapped[Plan] = relationship(lazy="joined")

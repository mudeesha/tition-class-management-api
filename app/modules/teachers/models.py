from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin
from app.modules.branches.models import Branch
from app.modules.users.models import Membership

teacher_branches = Table(
    "teacher_branches",
    Base.metadata,
    Column("teacher_id", ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
)


class Teacher(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nic"),
        CheckConstraint("institute_share_percent BETWEEN 0 AND 100", name="share_range"),
    )

    # Set when the teacher can sign in. Many teachers never do.
    membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), unique=True
    )
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    nic: Mapped[str | None] = mapped_column(String(20))
    # Institute's cut of this teacher's class fees. 0 means the teacher keeps it all.
    institute_share_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    membership: Mapped[Membership | None] = relationship(lazy="joined")
    branches: Mapped[list[Branch]] = relationship(
        secondary=teacher_branches, lazy="selectin", order_by=Branch.name
    )

    @property
    def branch_ids(self) -> list[int]:
        return [b.id for b in self.branches]

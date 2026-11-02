from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin


class Branch(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(10))  # KDY, GAL; used on receipt numbers later
    city: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # The branch created with the tenant. Individual teachers only ever have this one,
    # and the UI hides branches for them.
    is_default: Mapped[bool] = mapped_column(default=False, server_default=false())


class Hall(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "halls"
    __table_args__ = (UniqueConstraint("branch_id", "name"),)

    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    branch: Mapped[Branch] = relationship(lazy="joined")

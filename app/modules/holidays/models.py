from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, IdMixin, TenantMixin, TimestampMixin
from app.modules.branches.models import Branch


class Holiday(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("tenant_id", "branch_id", "date", postgresql_nulls_not_distinct=True),
    )

    # Empty means the holiday applies to every branch.
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(150))

    branch: Mapped[Branch | None] = relationship(lazy="joined")

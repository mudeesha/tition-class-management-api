from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, str_enum


class DiscountStacking(StrEnum):
    BOTH = "both"  # half card + late join → 25% of the fee
    BEST_ONLY = "best_only"  # only the larger discount → 50% of the fee


class InstituteSettings(TimestampMixin, Base):
    """Fee rules each institute sets for itself. One row per tenant."""

    __tablename__ = "institute_settings"
    __table_args__ = (
        CheckConstraint(
            "late_join_discount_percent BETWEEN 0 AND 100", name="late_join_discount_range"
        ),
        CheckConstraint("tute_institute_share_percent BETWEEN 0 AND 100", name="tute_share_range"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    admission_fee: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    # A student who first joins a class on or after this day pays the late-join rate
    # for that first month.
    late_join_from_day: Mapped[int] = mapped_column(Integer, default=15)
    late_join_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("50")
    )
    # Door scan for an unpaid month: warning up to this day, blocked after it.
    warning_until_day: Mapped[int] = mapped_column(Integer, default=14)
    discount_stacking: Mapped[DiscountStacking] = mapped_column(
        str_enum(DiscountStacking), default=DiscountStacking.BOTH
    )
    # Institute's cut of paid-tute money. 0 means the teacher keeps it all.
    tute_institute_share_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )

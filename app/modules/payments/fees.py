"""The fee rules, in one place. Dues, receipts and the door scan all use these."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.common.schemas import add_months
from app.modules.institute.models import DiscountStacking, InstituteSettings
from app.modules.students.models import CardType, Enrollment

CARD_DISCOUNT = {CardType.FULL: Decimal(0), CardType.HALF: Decimal(50), CardType.FREE: Decimal(100)}
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Charge:
    full_amount: Decimal
    amount: Decimal
    card_type: CardType
    late_join: bool  # the late-join discount was applied


def is_late_join(enrollment: Enrollment, month: date, settings: InstituteSettings) -> bool:
    """The first month of a student who started on or after the late-join day (default 15th).

    Promotions start on the 1st, so moving up never counts as a late join.
    """
    return (
        month == enrollment.start_month and enrollment.joined_on.day >= settings.late_join_from_day
    )


def month_charge(enrollment: Enrollment, month: date, settings: InstituteSettings) -> Charge:
    """What one month of a class costs this student.

    Half card = 50% off, free card = 100% off. With a late join too, `discount_stacking`
    decides: "both" applies one after the other (half + late 50% → pays 25%), "best_only"
    applies only the bigger one (→ pays 50%).
    """
    fee = enrollment.tuition_class.monthly_fee
    card = CARD_DISCOUNT[enrollment.card_type]
    late = settings.late_join_discount_percent if is_late_join(enrollment, month, settings) else 0
    late = Decimal(late)

    if settings.discount_stacking == DiscountStacking.BOTH:
        share = (1 - card / HUNDRED) * (1 - late / HUNDRED)
        late_applied = late > 0
    else:
        share = 1 - max(card, late) / HUNDRED
        late_applied = late > card

    amount = (fee * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Charge(fee, amount, enrollment.card_type, late_applied)


def months(first: date, last: date) -> list[date]:
    """Every month from `first` to `last`, both included (first days of months)."""
    result, month = [], first
    while month <= last:
        result.append(month)
        month = add_months(month, 1)
    return result


def attends_in(enrollment: Enrollment, month: date) -> bool:
    return enrollment.start_month <= month and (
        enrollment.end_month is None or month <= enrollment.end_month
    )

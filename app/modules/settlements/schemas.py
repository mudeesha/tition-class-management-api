import datetime as dt

from pydantic import Field

from app.common.schemas import Money, Month, Percent, Schema, SignedMoney
from app.modules.classes.schemas import TeacherRef
from app.modules.payments.models import PaymentMethod, PaymentStatus
from app.modules.payments.schemas import UserRef


class SettlementRow(Schema):
    """One teacher's month. Money is counted in the month it was received."""

    teacher: TeacherRef
    share_percent: Percent = Field(description="The institute's share on the teacher's profile now")
    class_fees: Money
    tutes: Money
    collected: Money
    institute_share: Money
    teacher_share: Money
    paid: Money = Field(description="Payouts recorded for this month")
    balance: SignedMoney = Field(
        description="Teacher's share minus payouts; negative if paid ahead"
    )


class SettlementOut(Schema):
    month: Month
    rows: list[SettlementRow]
    collected: Money
    institute_share: Money
    teacher_share: Money
    paid: Money


class TeacherMonth(Schema):
    month: Month
    collected: Money
    teacher_share: Money
    paid: Money


class PayoutCreate(Schema):
    teacher_id: int
    month: Month
    amount: Money = Field(gt=0)
    method: PaymentMethod = PaymentMethod.CASH
    note: str | None = Field(None, max_length=255)


class VoidIn(Schema):
    reason: str = Field(min_length=3, max_length=255)


class PayoutOut(Schema):
    id: int
    teacher: TeacherRef
    month: Month
    amount: Money
    method: PaymentMethod
    note: str | None
    paid_at: dt.datetime
    paid_by: UserRef
    status: PaymentStatus
    void_reason: str | None


class TeacherSettlementOut(Schema):
    teacher: TeacherRef
    share_percent: Percent
    owed: SignedMoney = Field(description="All shares minus all payouts, to date")
    months: list[TeacherMonth] = Field(description="Latest first")
    payouts: list[PayoutOut]

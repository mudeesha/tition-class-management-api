import datetime as dt
from typing import Annotated, Literal

from pydantic import Field

from app.common.schemas import Money, Month, Schema
from app.modules.branches.schemas import BranchRef
from app.modules.classes.schemas import ClassRef
from app.modules.payments.models import ItemKind, PaymentMethod, PaymentStatus
from app.modules.students.models import CardType
from app.modules.students.schemas import StudentRef


class UserRef(Schema):
    id: int
    name: str


# What a student owes


class DueMonth(Schema):
    enrollment_id: int
    tuition_class: ClassRef
    month: Month
    full_amount: Money
    amount: Money
    card_type: CardType
    late_join: bool


class DueTute(Schema):
    tute_id: int
    title: str
    month: Month
    price: Money


class DuesOut(Schema):
    admission_fee: Money | None = Field(description="Set while the admission fee is unpaid")
    months: list[DueMonth] = Field(description="Unpaid months up to `until`, oldest first")
    total: Money = Field(description="Admission and class fees (not tutes)")
    tutes: list[DueTute] = Field(
        [], description="Paid tutes of the student's classes not bought yet. Optional."
    )


# Receipts


class MonthlyItemIn(Schema):
    kind: Literal["monthly"]
    enrollment_id: int
    month: Month


class AdmissionItemIn(Schema):
    kind: Literal["admission"]


class TuteItemIn(Schema):
    kind: Literal["tute"]
    tute_id: int


ItemIn = Annotated[MonthlyItemIn | AdmissionItemIn | TuteItemIn, Field(discriminator="kind")]


class PaymentCreate(Schema):
    """What is being paid for. The server works out every amount from the fee rules."""

    student_id: int
    branch_id: int = Field(
        description="Where the money is collected; the receipt is numbered there"
    )
    method: PaymentMethod = PaymentMethod.CASH
    items: list[ItemIn] = Field(min_length=1)
    note: str | None = Field(None, max_length=255)


class VoidIn(Schema):
    reason: str = Field(min_length=3, max_length=255)


class TuteRef(Schema):
    id: int
    title: str


class PaymentItemOut(Schema):
    id: int
    kind: ItemKind
    tuition_class: ClassRef | None
    tute: TuteRef | None
    month: Month | None
    full_amount: Money
    amount: Money
    card_type: CardType | None
    late_join: bool


class PaymentOut(Schema):
    id: int
    receipt_no: str
    branch: BranchRef
    student: StudentRef
    amount: Money
    method: PaymentMethod
    paid_at: dt.datetime
    collected_by: UserRef
    note: str | None
    status: PaymentStatus
    void_reason: str | None
    voided_by: UserRef | None
    voided_at: dt.datetime | None
    handover_id: int | None
    items: list[PaymentItemOut]


# Cash handover


class CashInHandOut(Schema):
    collected_by: UserRef
    branch: BranchRef
    amount: Money
    receipts: int


class HandoverCreate(Schema):
    collected_by_id: int = Field(description="The user handing the cash over")
    branch_id: int
    note: str | None = Field(None, max_length=255)


class HandoverOut(Schema):
    id: int
    branch: BranchRef
    collected_by: UserRef
    received_by: UserRef
    amount: Money
    handed_at: dt.datetime
    note: str | None

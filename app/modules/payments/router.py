import datetime as dt

from fastapi import APIRouter, status

from app.common.schemas import Month, Page, PageQuery
from app.modules.payments.dependencies import CashServiceDep, PaymentServiceDep
from app.modules.payments.models import PaymentStatus
from app.modules.payments.schemas import (
    CashInHandOut,
    DuesOut,
    HandoverCreate,
    HandoverOut,
    PaymentCreate,
    PaymentOut,
    VoidIn,
)
from app.tenancy.context import requires

router = APIRouter(tags=["Payments"])
cash_router = APIRouter(prefix="/cash", tags=["Cash handover"])


@router.get(
    "/students/{student_id}/dues",
    response_model=DuesOut,
    dependencies=[requires("payments.view")],
)
def dues(student_id: int, service: PaymentServiceDep, until: Month | None = None):
    """Unpaid months up to `until` (YYYY-MM, default this month) and the admission fee if unpaid.

    Amounts include half/free cards and the late-join discount.
    """
    return service.dues(student_id, until)


@router.get("/payments", response_model=Page[PaymentOut], dependencies=[requires("payments.view")])
def list_payments(
    service: PaymentServiceDep,
    page: PageQuery,
    q: str | None = None,
    branch_id: int | None = None,
    student_id: int | None = None,
    status: PaymentStatus | None = None,
    collected_by_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
):
    """Newest first. `q` matches the receipt number."""
    return service.list(page, q, branch_id, student_id, status, collected_by_id, date_from, date_to)


@router.post(
    "/payments",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("payments.create")],
)
def collect(data: PaymentCreate, service: PaymentServiceDep):
    """Records a payment and returns the receipt. 409 if a month is already paid."""
    return service.create(data)


@router.get(
    "/payments/{payment_id}", response_model=PaymentOut, dependencies=[requires("payments.view")]
)
def get_payment(payment_id: int, service: PaymentServiceDep):
    return service.get(payment_id)


@router.post(
    "/payments/{payment_id}/void",
    response_model=PaymentOut,
    dependencies=[requires("payments.void")],
)
def void_payment(payment_id: int, data: VoidIn, service: PaymentServiceDep):
    """Cancels a receipt. Its months become unpaid again."""
    return service.void(payment_id, data)


@cash_router.get(
    "/in-hand", response_model=list[CashInHandOut], dependencies=[requires("payments.view")]
)
def cash_in_hand(service: CashServiceDep, branch_id: int | None = None):
    """Cash collected and not handed over yet, per person and branch.

    People without `cash.receive` see only their own.
    """
    return service.in_hand(branch_id)


@cash_router.post(
    "/handovers",
    response_model=HandoverOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("cash.receive")],
)
def hand_over(data: HandoverCreate, service: CashServiceDep):
    """You take over all the cash one person collected at a branch."""
    return service.hand_over(data)


@cash_router.get(
    "/handovers", response_model=Page[HandoverOut], dependencies=[requires("payments.view")]
)
def handovers(
    service: CashServiceDep,
    page: PageQuery,
    branch_id: int | None = None,
    collected_by_id: int | None = None,
):
    return service.history(page, branch_id, collected_by_id)

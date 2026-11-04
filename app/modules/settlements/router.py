from fastapi import APIRouter, status

from app.common.schemas import Month
from app.modules.settlements.dependencies import SettlementServiceDep
from app.modules.settlements.schemas import (
    PayoutCreate,
    PayoutOut,
    SettlementOut,
    TeacherSettlementOut,
    VoidIn,
)
from app.tenancy.context import requires

router = APIRouter(tags=["Teacher settlements"])


@router.get(
    "/settlements", response_model=SettlementOut, dependencies=[requires("settlements.view")]
)
def month_settlement(month: Month, service: SettlementServiceDep):
    """Every teacher's collections, institute and teacher shares, payouts and balance for a
    month (YYYY-MM). Needs access to all branches."""
    return service.month(month)


@router.get(
    "/settlements/teachers/{teacher_id}",
    response_model=TeacherSettlementOut,
    dependencies=[requires("settlements.view")],
)
def teacher_settlement(teacher_id: int, service: SettlementServiceDep):
    """One teacher, month by month, with every payout and what is still owed."""
    return service.teacher(teacher_id)


@router.post(
    "/payouts",
    response_model=PayoutOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("settlements.pay")],
)
def pay_teacher(data: PayoutCreate, service: SettlementServiceDep):
    return service.pay(data)


@router.post(
    "/payouts/{payout_id}/void",
    response_model=PayoutOut,
    dependencies=[requires("settlements.pay")],
)
def void_payout(payout_id: int, data: VoidIn, service: SettlementServiceDep):
    return service.void(payout_id, data)

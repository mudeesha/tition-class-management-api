from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.payments.service import CashService, PaymentService
from app.tenancy.context import CurrentContext


def get_payment_service(db: DbSession, ctx: CurrentContext) -> PaymentService:
    return PaymentService(db, ctx)


def get_cash_service(db: DbSession, ctx: CurrentContext) -> CashService:
    return CashService(db, ctx)


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
CashServiceDep = Annotated[CashService, Depends(get_cash_service)]

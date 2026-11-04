from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.settlements.service import SettlementService
from app.tenancy.context import CurrentContext


def get_settlement_service(db: DbSession, ctx: CurrentContext) -> SettlementService:
    return SettlementService(db, ctx)


SettlementServiceDep = Annotated[SettlementService, Depends(get_settlement_service)]

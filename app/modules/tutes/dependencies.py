from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.tutes.service import TuteService
from app.tenancy.context import CurrentContext


def get_tute_service(db: DbSession, ctx: CurrentContext) -> TuteService:
    return TuteService(db, ctx)


TuteServiceDep = Annotated[TuteService, Depends(get_tute_service)]

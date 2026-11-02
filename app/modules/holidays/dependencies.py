from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.holidays.service import HolidayService
from app.tenancy.context import CurrentContext


def get_holiday_service(db: DbSession, ctx: CurrentContext) -> HolidayService:
    return HolidayService(db, ctx)


HolidayServiceDep = Annotated[HolidayService, Depends(get_holiday_service)]

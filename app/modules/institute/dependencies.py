from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.institute.service import InstituteService
from app.tenancy.context import CurrentContext


def get_institute_service(db: DbSession, ctx: CurrentContext) -> InstituteService:
    return InstituteService(db, ctx)


InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]

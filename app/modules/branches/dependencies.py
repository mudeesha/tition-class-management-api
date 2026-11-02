from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.branches.service import BranchService, HallService
from app.tenancy.context import CurrentContext


def get_branch_service(db: DbSession, ctx: CurrentContext) -> BranchService:
    return BranchService(db, ctx)


def get_hall_service(db: DbSession, ctx: CurrentContext) -> HallService:
    return HallService(db, ctx)


BranchServiceDep = Annotated[BranchService, Depends(get_branch_service)]
HallServiceDep = Annotated[HallService, Depends(get_hall_service)]

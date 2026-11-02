from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.users.service import MemberService, RoleService
from app.tenancy.context import CurrentContext


def get_role_service(db: DbSession, ctx: CurrentContext) -> RoleService:
    return RoleService(db, ctx)


def get_member_service(db: DbSession, ctx: CurrentContext) -> MemberService:
    return MemberService(db, ctx)


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
MemberServiceDep = Annotated[MemberService, Depends(get_member_service)]

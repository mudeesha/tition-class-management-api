from fastapi import APIRouter, status

from app.common.schemas import Page, PageQuery
from app.modules.users.dependencies import MemberServiceDep, RoleServiceDep
from app.modules.users.schemas import (
    MemberCreate,
    MemberOut,
    MemberUpdate,
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from app.tenancy.context import requires

permissions_router = APIRouter(prefix="/permissions", tags=["Roles & permissions"])
roles_router = APIRouter(prefix="/roles", tags=["Roles & permissions"])
members_router = APIRouter(prefix="/members", tags=["Members"])


@permissions_router.get(
    "", response_model=list[PermissionOut], dependencies=[requires("roles.view")]
)
def list_permissions(service: RoleServiceDep):
    return service.all_permissions()


@roles_router.get("", response_model=list[RoleOut], dependencies=[requires("roles.view")])
def list_roles(service: RoleServiceDep):
    return service.list()


@roles_router.post(
    "",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("roles.manage")],
)
def create_role(data: RoleCreate, service: RoleServiceDep):
    return service.create(data)


@roles_router.get("/{role_id}", response_model=RoleOut, dependencies=[requires("roles.view")])
def get_role(role_id: int, service: RoleServiceDep):
    return service.get(role_id)


@roles_router.patch("/{role_id}", response_model=RoleOut, dependencies=[requires("roles.manage")])
def update_role(role_id: int, data: RoleUpdate, service: RoleServiceDep):
    return service.update(role_id, data)


@roles_router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("roles.manage")],
)
def delete_role(role_id: int, service: RoleServiceDep):
    service.delete(role_id)


@members_router.get("", response_model=Page[MemberOut], dependencies=[requires("members.view")])
def list_members(
    service: MemberServiceDep,
    page: PageQuery,
    q: str | None = None,
    role_id: int | None = None,
    is_active: bool | None = None,
):
    return service.list(page, q, role_id, is_active)


@members_router.post(
    "",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("members.manage")],
)
def create_member(data: MemberCreate, service: MemberServiceDep):
    return service.create(data)


@members_router.get(
    "/{member_id}", response_model=MemberOut, dependencies=[requires("members.view")]
)
def get_member(member_id: int, service: MemberServiceDep):
    return service.get(member_id)


@members_router.patch(
    "/{member_id}", response_model=MemberOut, dependencies=[requires("members.manage")]
)
def update_member(member_id: int, data: MemberUpdate, service: MemberServiceDep):
    return service.update(member_id, data)

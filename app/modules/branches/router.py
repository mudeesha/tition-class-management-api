from fastapi import APIRouter, status

from app.modules.branches.dependencies import BranchServiceDep, HallServiceDep
from app.modules.branches.schemas import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    HallCreate,
    HallOut,
    HallUpdate,
)
from app.tenancy.context import requires

router = APIRouter(prefix="/branches", tags=["Branches"])
halls_router = APIRouter(prefix="/halls", tags=["Halls"])


@router.get("", response_model=list[BranchOut], dependencies=[requires("branches.view")])
def list_branches(service: BranchServiceDep):
    return service.list()


@router.post(
    "",
    response_model=BranchOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("branches.manage")],
)
def create_branch(data: BranchCreate, service: BranchServiceDep):
    return service.create(data)


@router.get("/{branch_id}", response_model=BranchOut, dependencies=[requires("branches.view")])
def get_branch(branch_id: int, service: BranchServiceDep):
    return service.get(branch_id)


@router.patch("/{branch_id}", response_model=BranchOut, dependencies=[requires("branches.manage")])
def update_branch(branch_id: int, data: BranchUpdate, service: BranchServiceDep):
    return service.update(branch_id, data)


@halls_router.get("", response_model=list[HallOut], dependencies=[requires("halls.view")])
def list_halls(service: HallServiceDep, branch_id: int | None = None):
    return service.list(branch_id)


@halls_router.post(
    "",
    response_model=HallOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("halls.manage")],
)
def create_hall(data: HallCreate, service: HallServiceDep):
    return service.create(data)


@halls_router.get("/{hall_id}", response_model=HallOut, dependencies=[requires("halls.view")])
def get_hall(hall_id: int, service: HallServiceDep):
    return service.get(hall_id)


@halls_router.patch("/{hall_id}", response_model=HallOut, dependencies=[requires("halls.manage")])
def update_hall(hall_id: int, data: HallUpdate, service: HallServiceDep):
    return service.update(hall_id, data)


@halls_router.delete(
    "/{hall_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("halls.manage")],
)
def delete_hall(hall_id: int, service: HallServiceDep):
    service.delete(hall_id)

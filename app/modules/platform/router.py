"""Platform admin (you, the system seller): plans and institutes."""

from fastapi import APIRouter, Depends, status

from app.common.schemas import Page, PageQuery
from app.modules.platform.dependencies import PlatformServiceDep
from app.modules.platform.models import TenantStatus
from app.modules.platform.schemas import (
    PlanCreate,
    PlanOut,
    PlanUpdate,
    PlatformSummary,
    TenantCreate,
    TenantOut,
    TenantUpdate,
)
from app.tenancy.context import get_platform_admin

router = APIRouter(
    prefix="/platform", tags=["Platform admin"], dependencies=[Depends(get_platform_admin)]
)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(service: PlatformServiceDep):
    return service.list_plans()


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanCreate, service: PlatformServiceDep):
    return service.create_plan(data)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, data: PlanUpdate, service: PlatformServiceDep):
    return service.update_plan(plan_id, data)


@router.get("/tenants", response_model=Page[TenantOut])
def list_tenants(
    service: PlatformServiceDep,
    page: PageQuery,
    q: str | None = None,
    status: TenantStatus | None = None,
):
    return service.list_tenants(page, q, status)


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(data: TenantCreate, service: PlatformServiceDep):
    return service.create_tenant(data)


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int, service: PlatformServiceDep):
    return service.tenant_out(tenant_id)


@router.get("/summary", response_model=PlatformSummary)
def summary(service: PlatformServiceDep):
    """Institutes by status, monthly revenue from active ones, and active students overall."""
    return service.summary()


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, data: TenantUpdate, service: PlatformServiceDep):
    return service.update_tenant(tenant_id, data)

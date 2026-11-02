from fastapi import APIRouter

from app.modules.auth.dependencies import AuthServiceDep
from app.modules.auth.schemas import (
    ChangePasswordIn,
    ContextOut,
    LoginIn,
    MeOut,
    RefreshIn,
    TokenOut,
)
from app.tenancy.context import CurrentContext, CurrentUser

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, service: AuthServiceDep):
    return service.login(data)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, service: AuthServiceDep):
    return service.refresh(data.refresh_token)


@router.post("/change-password", response_model=TokenOut)
def change_password(data: ChangePasswordIn, user: CurrentUser, service: AuthServiceDep):
    return service.change_password(user, data)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, service: AuthServiceDep):
    """The signed-in user and the institutes they belong to."""
    return service.me(user)


@router.get("/context", response_model=ContextOut)
def context(ctx: CurrentContext, service: AuthServiceDep):
    """Role, permissions and branches in the institute chosen with X-Tenant-ID."""
    return service.context(ctx)

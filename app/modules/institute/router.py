from fastapi import APIRouter

from app.modules.institute.dependencies import InstituteServiceDep
from app.modules.institute.schemas import InstituteOut, InstituteUpdate, SettingsOut, SettingsUpdate
from app.tenancy.context import requires

router = APIRouter(tags=["Institute"])


@router.get("/institute", response_model=InstituteOut, dependencies=[requires("settings.view")])
def get_profile(service: InstituteServiceDep):
    return service.profile()


@router.patch("/institute", response_model=InstituteOut, dependencies=[requires("settings.update")])
def update_profile(data: InstituteUpdate, service: InstituteServiceDep):
    return service.update_profile(data)


@router.get("/settings", response_model=SettingsOut, dependencies=[requires("settings.view")])
def get_settings(service: InstituteServiceDep):
    """Fee rules: admission fee, late join, door-scan warning, discount stacking, tute share."""
    return service.get_settings()


@router.patch("/settings", response_model=SettingsOut, dependencies=[requires("settings.update")])
def update_settings(data: SettingsUpdate, service: InstituteServiceDep):
    return service.update_settings(data)

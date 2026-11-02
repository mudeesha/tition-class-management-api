import datetime as dt

from fastapi import APIRouter, status

from app.modules.holidays.dependencies import HolidayServiceDep
from app.modules.holidays.schemas import HolidayCreate, HolidayOut, HolidayUpdate
from app.tenancy.context import requires

router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.get("", response_model=list[HolidayOut], dependencies=[requires("holidays.view")])
def list_holidays(
    service: HolidayServiceDep,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    branch_id: int | None = None,
):
    return service.list(date_from, date_to, branch_id)


@router.post(
    "",
    response_model=HolidayOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("holidays.manage")],
)
def create_holiday(data: HolidayCreate, service: HolidayServiceDep):
    return service.create(data)


@router.get("/{holiday_id}", response_model=HolidayOut, dependencies=[requires("holidays.view")])
def get_holiday(holiday_id: int, service: HolidayServiceDep):
    return service.get(holiday_id)


@router.patch(
    "/{holiday_id}", response_model=HolidayOut, dependencies=[requires("holidays.manage")]
)
def update_holiday(holiday_id: int, data: HolidayUpdate, service: HolidayServiceDep):
    return service.update(holiday_id, data)


@router.delete(
    "/{holiday_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("holidays.manage")],
)
def delete_holiday(holiday_id: int, service: HolidayServiceDep):
    service.delete(holiday_id)

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends

from app.common.schemas import Month
from app.core.database import DbSession
from app.modules.reports.schemas import (
    AttendanceReport,
    CollectionsReport,
    DashboardOut,
    DuesReport,
)
from app.modules.reports.service import ReportService
from app.tenancy.context import CurrentContext, requires

router = APIRouter(tags=["Dashboard and reports"])


def get_report_service(db: DbSession, ctx: CurrentContext) -> ReportService:
    return ReportService(db, ctx)


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(service: ReportServiceDep, branch_id: int | None = None):
    """Today's classes, collections and unpaid fees, as far as your permissions allow."""
    return service.dashboard(branch_id)


@router.get(
    "/reports/dues",
    response_model=DuesReport,
    dependencies=[requires("reports.view"), requires("payments.view")],
)
def dues_report(
    service: ReportServiceDep, branch_id: int | None = None, class_id: int | None = None
):
    """Students who owe class fees up to this month, with phone numbers to follow up."""
    return service.dues(branch_id, class_id)


@router.get(
    "/reports/collections",
    response_model=CollectionsReport,
    dependencies=[requires("reports.view"), requires("payments.view")],
)
def collections_report(
    service: ReportServiceDep, date_from: dt.date, date_to: dt.date, branch_id: int | None = None
):
    """Valid receipts per day and payment method, and the split by class fees, admission, tutes."""
    return service.collections(date_from, date_to, branch_id)


@router.get(
    "/reports/attendance",
    response_model=AttendanceReport,
    dependencies=[requires("reports.view"), requires("attendance.view")],
)
def attendance_report(service: ReportServiceDep, month: Month, branch_id: int | None = None):
    return service.attendance(month, branch_id)

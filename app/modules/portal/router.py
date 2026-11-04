"""The student portal. Every endpoint is about the signed-in student only."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.database import DbSession
from app.modules.attendance.schemas import AttendanceOut
from app.modules.payments.schemas import DuesOut, PaymentOut
from app.modules.portal.schemas import PortalExamOut, PortalTuteOut
from app.modules.portal.service import PortalService
from app.modules.students.schemas import StudentProfileOut
from app.tenancy.context import CurrentContext, requires

router = APIRouter(prefix="/portal", tags=["Student portal"])


def get_portal_service(db: DbSession, ctx: CurrentContext) -> PortalService:
    return PortalService(db, ctx)


PortalDep = Annotated[PortalService, Depends(get_portal_service)]


@router.get("/me", response_model=StudentProfileOut)
def me(service: PortalDep):
    """Your details and classes."""
    return service.me()


@router.get("/dues", response_model=DuesOut, dependencies=[requires("portal.payments")])
def dues(service: PortalDep):
    return service.dues()


@router.get(
    "/receipts", response_model=list[PaymentOut], dependencies=[requires("portal.payments")]
)
def receipts(service: PortalDep):
    return service.receipts()


@router.get(
    "/attendance", response_model=list[AttendanceOut], dependencies=[requires("portal.attendance")]
)
def attendance(service: PortalDep, date_from: dt.date, date_to: dt.date):
    return service.attendance(date_from, date_to)


@router.get("/tutes", response_model=list[PortalTuteOut], dependencies=[requires("portal.tutes")])
def tutes(service: PortalDep):
    """Tutes of your classes, and whether you can have each one yet."""
    return service.tutes()


@router.get("/tutes/{tute_id}/file", dependencies=[requires("portal.tutes")])
def tute_file(tute_id: int, service: PortalDep):
    """Downloads the soft copy, if your class fee (and the tute price, for paid tutes) is paid."""
    path, name = service.tute_file(tute_id)
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get("/exams", response_model=list[PortalExamOut], dependencies=[requires("portal.marks")])
def exams(service: PortalDep):
    """Your marks and ranks in published exams."""
    return service.exams()

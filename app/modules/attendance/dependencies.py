from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.attendance.service import AttendanceService, SessionService
from app.tenancy.context import CurrentContext


def get_session_service(db: DbSession, ctx: CurrentContext) -> SessionService:
    return SessionService(db, ctx)


def get_attendance_service(db: DbSession, ctx: CurrentContext) -> AttendanceService:
    return AttendanceService(db, ctx)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
AttendanceServiceDep = Annotated[AttendanceService, Depends(get_attendance_service)]

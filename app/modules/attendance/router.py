import datetime as dt

from fastapi import APIRouter, status

from app.core import clock
from app.modules.attendance.dependencies import AttendanceServiceDep, SessionServiceDep
from app.modules.attendance.schemas import (
    AttendanceOut,
    ExtraSessionIn,
    MarkAllIn,
    RosterRow,
    ScanIn,
    ScanOut,
    SessionOut,
    SessionUpdate,
)
from app.tenancy.context import requires

router = APIRouter(tags=["Attendance"])


@router.get(
    "/sessions", response_model=list[SessionOut], dependencies=[requires("attendance.view")]
)
def list_sessions(
    service: SessionServiceDep,
    date_from: dt.date,
    date_to: dt.date,
    class_id: int | None = None,
    branch_id: int | None = None,
):
    """Class days in a date range (up to 62 days), with attendance counts.

    Regular days come from the weekly times and skip holidays.
    """
    return service.list(date_from, date_to, class_id, branch_id)


@router.get(
    "/sessions/today", response_model=list[SessionOut], dependencies=[requires("attendance.view")]
)
def today(service: SessionServiceDep, branch_id: int | None = None):
    day = clock.today()
    return service.list(day, day, branch_id=branch_id)


@router.get(
    "/sessions/{session_id}", response_model=SessionOut, dependencies=[requires("attendance.view")]
)
def get_day(session_id: int, service: SessionServiceDep):
    return service.detail(session_id)


@router.post(
    "/classes/{class_id}/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("classes.manage")],
)
def add_extra_day(class_id: int, data: ExtraSessionIn, service: SessionServiceDep):
    """An extra class on one day. Checked for hall and teacher clashes on that day."""
    return service.add_extra(class_id, data)


@router.patch(
    "/sessions/{session_id}", response_model=SessionOut, dependencies=[requires("classes.manage")]
)
def update_day(session_id: int, data: SessionUpdate, service: SessionServiceDep):
    """Cancel (`status: cancelled`) or restore a day, or change its time or hall."""
    return service.update(session_id, data)


@router.get(
    "/sessions/{session_id}/attendance",
    response_model=list[RosterRow],
    dependencies=[requires("attendance.view")],
)
def roster(session_id: int, service: AttendanceServiceDep):
    """The class's students on that day, with fee status and attendance."""
    return service.roster(session_id)


@router.put(
    "/sessions/{session_id}/attendance",
    response_model=list[RosterRow],
    dependencies=[requires("attendance.mark")],
)
def mark(session_id: int, data: MarkAllIn, service: AttendanceServiceDep):
    """Marks students by hand. 422 `fee_blocked` if an unpaid student past the warning
    days is marked present or late."""
    return service.mark(session_id, data)


@router.post("/attendance/scan", response_model=ScanOut, dependencies=[requires("attendance.mark")])
def scan(data: ScanIn, service: AttendanceServiceDep):
    """A student's card scanned at the door. See `outcome` for what happened."""
    return service.scan(data)


@router.get(
    "/attendance", response_model=list[AttendanceOut], dependencies=[requires("attendance.view")]
)
def student_attendance(
    service: AttendanceServiceDep, student_id: int, date_from: dt.date, date_to: dt.date
):
    return service.history(student_id, date_from, date_to)

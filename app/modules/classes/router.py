from fastapi import APIRouter, status

from app.common.schemas import Page, PageQuery
from app.modules.classes.dependencies import ClassServiceDep
from app.modules.classes.models import ClassLevel
from app.modules.classes.schemas import (
    ClassCreate,
    ClassOut,
    ClassUpdate,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
    TimetableEntryOut,
)
from app.tenancy.context import requires

router = APIRouter(prefix="/classes", tags=["Classes"])
schedules_router = APIRouter(prefix="/schedules", tags=["Classes"])
timetable_router = APIRouter(prefix="/timetable", tags=["Classes"])


@router.get("", response_model=Page[ClassOut], dependencies=[requires("classes.view")])
def list_classes(
    service: ClassServiceDep,
    page: PageQuery,
    q: str | None = None,
    branch_id: int | None = None,
    teacher_id: int | None = None,
    subject_id: int | None = None,
    level: ClassLevel | None = None,
    exam_year: int | None = None,
    is_active: bool | None = None,
):
    return service.list(page, q, branch_id, teacher_id, subject_id, level, exam_year, is_active)


@router.post(
    "",
    response_model=ClassOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("classes.manage")],
)
def create_class(data: ClassCreate, service: ClassServiceDep):
    return service.create(data)


@router.get("/{class_id}", response_model=ClassOut, dependencies=[requires("classes.view")])
def get_class(class_id: int, service: ClassServiceDep):
    return service.get(class_id)


@router.patch("/{class_id}", response_model=ClassOut, dependencies=[requires("classes.manage")])
def update_class(class_id: int, data: ClassUpdate, service: ClassServiceDep):
    return service.update(class_id, data)


@router.post(
    "/{class_id}/schedules",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("classes.manage")],
)
def add_schedule(class_id: int, data: ScheduleCreate, service: ClassServiceDep):
    """Adds a weekly slot. Fails with 409 `hall_clash` or `teacher_clash` if it overlaps."""
    return service.add_schedule(class_id, data)


@schedules_router.patch(
    "/{schedule_id}", response_model=ScheduleOut, dependencies=[requires("classes.manage")]
)
def update_schedule(schedule_id: int, data: ScheduleUpdate, service: ClassServiceDep):
    return service.update_schedule(schedule_id, data)


@schedules_router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("classes.manage")],
)
def delete_schedule(schedule_id: int, service: ClassServiceDep):
    service.delete_schedule(schedule_id)


@timetable_router.get(
    "", response_model=list[TimetableEntryOut], dependencies=[requires("classes.view")]
)
def timetable(
    service: ClassServiceDep,
    branch_id: int | None = None,
    teacher_id: int | None = None,
    hall_id: int | None = None,
):
    """Every weekly slot of the active classes, by day and time."""
    return service.timetable(branch_id, teacher_id, hall_id)

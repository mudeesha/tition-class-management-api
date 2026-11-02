from fastapi import APIRouter, status

from app.common.schemas import Page, PageQuery
from app.modules.teachers.dependencies import TeacherServiceDep
from app.modules.teachers.schemas import TeacherCreate, TeacherOut, TeacherUpdate
from app.tenancy.context import requires

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.get("", response_model=Page[TeacherOut], dependencies=[requires("teachers.view")])
def list_teachers(
    service: TeacherServiceDep,
    page: PageQuery,
    q: str | None = None,
    branch_id: int | None = None,
    is_active: bool | None = None,
):
    return service.list(page, q, branch_id, is_active)


@router.post(
    "",
    response_model=TeacherOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("teachers.manage")],
)
def create_teacher(data: TeacherCreate, service: TeacherServiceDep):
    return service.create(data)


@router.get("/{teacher_id}", response_model=TeacherOut, dependencies=[requires("teachers.view")])
def get_teacher(teacher_id: int, service: TeacherServiceDep):
    return service.get(teacher_id)


@router.patch(
    "/{teacher_id}", response_model=TeacherOut, dependencies=[requires("teachers.manage")]
)
def update_teacher(teacher_id: int, data: TeacherUpdate, service: TeacherServiceDep):
    return service.update(teacher_id, data)

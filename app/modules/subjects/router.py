from fastapi import APIRouter, status

from app.modules.subjects.dependencies import SubjectServiceDep
from app.modules.subjects.models import SubjectLevel
from app.modules.subjects.schemas import SubjectCreate, SubjectOut, SubjectUpdate
from app.tenancy.context import requires

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("", response_model=list[SubjectOut], dependencies=[requires("subjects.view")])
def list_subjects(service: SubjectServiceDep, level: SubjectLevel | None = None):
    return service.list(level)


@router.post(
    "",
    response_model=SubjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("subjects.manage")],
)
def create_subject(data: SubjectCreate, service: SubjectServiceDep):
    return service.create(data)


@router.get("/{subject_id}", response_model=SubjectOut, dependencies=[requires("subjects.view")])
def get_subject(subject_id: int, service: SubjectServiceDep):
    return service.get(subject_id)


@router.patch(
    "/{subject_id}", response_model=SubjectOut, dependencies=[requires("subjects.manage")]
)
def update_subject(subject_id: int, data: SubjectUpdate, service: SubjectServiceDep):
    return service.update(subject_id, data)


@router.delete(
    "/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("subjects.manage")],
)
def delete_subject(subject_id: int, service: SubjectServiceDep):
    service.delete(subject_id)

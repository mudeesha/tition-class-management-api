import datetime as dt

from fastapi import APIRouter, status

from app.common.schemas import Page, PageQuery
from app.modules.exams.dependencies import ExamServiceDep
from app.modules.exams.schemas import (
    ExamCreate,
    ExamOut,
    ExamUpdate,
    MarksIn,
    ResultsOut,
    SheetRow,
)
from app.tenancy.context import requires

router = APIRouter(prefix="/exams", tags=["Exams"])


@router.get("", response_model=Page[ExamOut], dependencies=[requires("exams.view")])
def list_exams(
    service: ExamServiceDep,
    page: PageQuery,
    q: str | None = None,
    class_id: int | None = None,
    teacher_id: int | None = None,
    subject_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
):
    return service.list(page, q, class_id, teacher_id, subject_id, date_from, date_to)


@router.post(
    "",
    response_model=ExamOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("exams.manage")],
)
def create_exam(data: ExamCreate, service: ExamServiceDep):
    return service.create(data)


@router.get("/{exam_id}", response_model=ExamOut, dependencies=[requires("exams.view")])
def get_exam(exam_id: int, service: ExamServiceDep):
    return service.get(exam_id)


@router.patch("/{exam_id}", response_model=ExamOut, dependencies=[requires("exams.manage")])
def update_exam(exam_id: int, data: ExamUpdate, service: ExamServiceDep):
    """`published: true` shows the results to students in the portal."""
    return service.update(exam_id, data)


@router.get(
    "/{exam_id}/marks", response_model=list[SheetRow], dependencies=[requires("exams.view")]
)
def marks_sheet(exam_id: int, service: ExamServiceDep):
    """Everyone in the exam's classes that month, with the marks entered so far."""
    return service.sheet(exam_id)


@router.put(
    "/{exam_id}/marks", response_model=list[SheetRow], dependencies=[requires("exams.manage")]
)
def save_marks(exam_id: int, data: MarksIn, service: ExamServiceDep):
    """Saves marks per student and part (or absent). Send only what changed."""
    return service.save_marks(exam_id, data)


@router.get("/{exam_id}/results", response_model=ResultsOut, dependencies=[requires("exams.view")])
def results(exam_id: int, service: ExamServiceDep):
    """Totals, percentages and ranks (overall and within each class)."""
    return service.results(exam_id)

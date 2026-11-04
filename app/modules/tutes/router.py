from fastapi import APIRouter, UploadFile, status
from fastapi.responses import FileResponse

from app.common.schemas import Month, Page, PageQuery
from app.modules.tutes.dependencies import TuteServiceDep
from app.modules.tutes.schemas import IssueIn, TuteCreate, TuteOut, TuteStudentOut, TuteUpdate
from app.modules.tutes.service import upload_limit
from app.tenancy.context import requires

router = APIRouter(prefix="/tutes", tags=["Tutes"])


@router.get("", response_model=Page[TuteOut], dependencies=[requires("tutes.view")])
def list_tutes(
    service: TuteServiceDep,
    page: PageQuery,
    q: str | None = None,
    month: Month | None = None,
    class_id: int | None = None,
    teacher_id: int | None = None,
):
    return service.list(page, q, month, class_id, teacher_id)


@router.post(
    "",
    response_model=TuteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("tutes.manage")],
)
def create_tute(data: TuteCreate, service: TuteServiceDep):
    return service.create(data)


@router.get("/{tute_id}", response_model=TuteOut, dependencies=[requires("tutes.view")])
def get_tute(tute_id: int, service: TuteServiceDep):
    return service.get(tute_id)


@router.patch("/{tute_id}", response_model=TuteOut, dependencies=[requires("tutes.manage")])
def update_tute(tute_id: int, data: TuteUpdate, service: TuteServiceDep):
    return service.update(tute_id, data)


@router.put("/{tute_id}/file", response_model=TuteOut, dependencies=[requires("tutes.manage")])
def upload_file(tute_id: int, file: UploadFile, service: TuteServiceDep):
    """Uploads the soft copy (a PDF, multipart form field `file`). Replaces any earlier one."""
    data = file.file.read(upload_limit() + 1)
    return service.upload(tute_id, data, file.filename)


@router.delete("/{tute_id}/file", response_model=TuteOut, dependencies=[requires("tutes.manage")])
def remove_file(tute_id: int, service: TuteServiceDep):
    return service.remove_file(tute_id)


@router.get("/{tute_id}/file", dependencies=[requires("tutes.view")])
def download_file(tute_id: int, service: TuteServiceDep):
    path, name = service.file(tute_id)
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get(
    "/{tute_id}/students",
    response_model=list[TuteStudentOut],
    dependencies=[requires("tutes.view")],
)
def tute_students(tute_id: int, service: TuteServiceDep):
    """Students of the tute's classes that month: whether they may have it, and if the hard
    copy was given. `reason` says why not: class_fee_unpaid or tute_unpaid."""
    return service.students(tute_id)


@router.post(
    "/{tute_id}/issues",
    response_model=TuteStudentOut,
    dependencies=[requires("tutes.issue")],
)
def give_hard_copy(tute_id: int, data: IssueIn, service: TuteServiceDep):
    """Ticks the hard copy as given. 422 if the student may not have the tute yet."""
    return service.issue(tute_id, data.student_id)


@router.delete(
    "/{tute_id}/issues/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires("tutes.issue")],
)
def take_back_tick(tute_id: int, student_id: int, service: TuteServiceDep):
    service.unissue(tute_id, student_id)

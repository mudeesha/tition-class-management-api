from fastapi import APIRouter, status

from app.common.schemas import Page, PageQuery
from app.modules.students.dependencies import EnrollmentServiceDep, StudentServiceDep
from app.modules.students.models import EnrollmentStatus
from app.modules.students.schemas import (
    EnrollmentCreate,
    EnrollmentOut,
    EnrollmentUpdate,
    LeaveIn,
    PortalAccountIn,
    PortalAccountOut,
    PromoteIn,
    PromoteOut,
    StudentCreate,
    StudentOut,
    StudentProfileOut,
    StudentUpdate,
)
from app.tenancy.context import requires

router = APIRouter(prefix="/students", tags=["Students"])
enrollments_router = APIRouter(prefix="/enrollments", tags=["Enrollments"])


@router.get("", response_model=Page[StudentOut], dependencies=[requires("students.view")])
def list_students(
    service: StudentServiceDep,
    page: PageQuery,
    q: str | None = None,
    branch_id: int | None = None,
    class_id: int | None = None,
    grade: int | None = None,
    is_active: bool | None = None,
):
    """`q` matches name, student code, phone or guardian's phone. `branch_id` finds students
    whose home branch it is or who attend a class there."""
    return service.list(page, q, branch_id, class_id, grade, is_active)


@router.post(
    "",
    response_model=StudentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("students.manage")],
)
def register_student(data: StudentCreate, service: StudentServiceDep):
    """Registers (admits) a student. The student code and QR card token are generated."""
    return service.create(data)


@router.get(
    "/{student_id}", response_model=StudentProfileOut, dependencies=[requires("students.view")]
)
def get_student(student_id: int, service: StudentServiceDep):
    return service.profile(student_id)


@router.patch(
    "/{student_id}", response_model=StudentOut, dependencies=[requires("students.manage")]
)
def update_student(student_id: int, data: StudentUpdate, service: StudentServiceDep):
    return service.update(student_id, data)


@router.post(
    "/{student_id}/new-card",
    response_model=StudentOut,
    dependencies=[requires("students.manage")],
)
def new_card(student_id: int, service: StudentServiceDep):
    """Gives the student a new QR code, e.g. when the card is lost. The old card stops working."""
    return service.new_qr(student_id)


@router.get(
    "/{student_id}/portal",
    response_model=PortalAccountOut,
    dependencies=[requires("students.view")],
)
def portal_account(student_id: int, service: StudentServiceDep):
    return service.portal_account(student_id)


@router.put(
    "/{student_id}/portal",
    response_model=PortalAccountOut,
    dependencies=[requires("students.manage")],
)
def set_portal_password(student_id: int, data: PortalAccountIn, service: StudentServiceDep):
    """Opens the student's portal login (username = their code) or resets its password.
    They must change the password when they first sign in."""
    return service.set_portal_password(student_id, data.password)


@router.delete(
    "/{student_id}/portal",
    response_model=PortalAccountOut,
    dependencies=[requires("students.manage")],
)
def close_portal(student_id: int, service: StudentServiceDep):
    return service.close_portal(student_id)


@enrollments_router.get(
    "", response_model=list[EnrollmentOut], dependencies=[requires("students.view")]
)
def list_enrollments(
    service: EnrollmentServiceDep,
    class_id: int | None = None,
    student_id: int | None = None,
    status: EnrollmentStatus | None = None,
):
    """A class's students (`class_id`) or a student's classes (`student_id`)."""
    return service.list(class_id, student_id, status)


@enrollments_router.post(
    "",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires("enrollments.manage")],
)
def enroll(data: EnrollmentCreate, service: EnrollmentServiceDep):
    """Adds a student to a class. Half and free cards need `enrollments.cards`."""
    return service.enroll(data)


@enrollments_router.post(
    "/promote", response_model=PromoteOut, dependencies=[requires("enrollments.manage")]
)
def promote(data: PromoteIn, service: EnrollmentServiceDep):
    """Moves a class's students to another class, e.g. Grade 6 → Grade 7 for the new year."""
    return service.promote(data)


@enrollments_router.patch(
    "/{enrollment_id}",
    response_model=EnrollmentOut,
    dependencies=[requires("enrollments.manage")],
)
def update_enrollment(enrollment_id: int, data: EnrollmentUpdate, service: EnrollmentServiceDep):
    """Changes the card type. Needs `enrollments.cards`."""
    return service.update(enrollment_id, data)


@enrollments_router.post(
    "/{enrollment_id}/leave",
    response_model=EnrollmentOut,
    dependencies=[requires("enrollments.manage")],
)
def leave(enrollment_id: int, data: LeaveIn, service: EnrollmentServiceDep):
    return service.leave(enrollment_id, data)

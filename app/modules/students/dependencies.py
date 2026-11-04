from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.students.service import EnrollmentService, StudentService
from app.tenancy.context import CurrentContext


def get_student_service(db: DbSession, ctx: CurrentContext) -> StudentService:
    return StudentService(db, ctx)


def get_enrollment_service(db: DbSession, ctx: CurrentContext) -> EnrollmentService:
    return EnrollmentService(db, ctx)


StudentServiceDep = Annotated[StudentService, Depends(get_student_service)]
EnrollmentServiceDep = Annotated[EnrollmentService, Depends(get_enrollment_service)]

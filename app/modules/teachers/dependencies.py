from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.teachers.service import TeacherService
from app.tenancy.context import CurrentContext


def get_teacher_service(db: DbSession, ctx: CurrentContext) -> TeacherService:
    return TeacherService(db, ctx)


TeacherServiceDep = Annotated[TeacherService, Depends(get_teacher_service)]

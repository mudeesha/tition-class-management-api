from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.subjects.service import SubjectService
from app.tenancy.context import CurrentContext


def get_subject_service(db: DbSession, ctx: CurrentContext) -> SubjectService:
    return SubjectService(db, ctx)


SubjectServiceDep = Annotated[SubjectService, Depends(get_subject_service)]

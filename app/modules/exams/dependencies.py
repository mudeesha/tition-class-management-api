from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.exams.service import ExamService
from app.tenancy.context import CurrentContext


def get_exam_service(db: DbSession, ctx: CurrentContext) -> ExamService:
    return ExamService(db, ctx)


ExamServiceDep = Annotated[ExamService, Depends(get_exam_service)]

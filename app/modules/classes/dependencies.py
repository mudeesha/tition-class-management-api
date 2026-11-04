from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.classes.service import ClassService
from app.tenancy.context import CurrentContext


def get_class_service(db: DbSession, ctx: CurrentContext) -> ClassService:
    return ClassService(db, ctx)


ClassServiceDep = Annotated[ClassService, Depends(get_class_service)]

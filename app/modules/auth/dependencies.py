from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.auth.service import AuthService


def get_auth_service(db: DbSession) -> AuthService:
    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

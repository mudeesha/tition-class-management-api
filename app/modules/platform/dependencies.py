from typing import Annotated

from fastapi import Depends

from app.core.database import DbSession
from app.modules.platform.service import PlatformService


def get_platform_service(db: DbSession) -> PlatformService:
    return PlatformService(db)


PlatformServiceDep = Annotated[PlatformService, Depends(get_platform_service)]

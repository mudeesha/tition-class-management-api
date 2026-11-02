from app.common.repository import TenantScopedRepository
from app.core.exceptions import NotFound
from app.modules.institute.models import InstituteSettings


class InstituteSettingsRepository(TenantScopedRepository[InstituteSettings]):
    model = InstituteSettings

    def current(self) -> InstituteSettings:
        settings = self.first()
        if settings is None:
            raise NotFound("Institute settings are missing")
        return settings

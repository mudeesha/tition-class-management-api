from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.institute.models import InstituteSettings
from app.modules.institute.repository import InstituteSettingsRepository
from app.modules.institute.schemas import InstituteUpdate, SettingsUpdate
from app.modules.platform.models import Tenant
from app.tenancy.context import TenantContext


class InstituteService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.settings = InstituteSettingsRepository(db, ctx)

    def profile(self) -> Tenant:
        return self.ctx.tenant

    def update_profile(self, data: InstituteUpdate) -> Tenant:
        tenant = self.ctx.tenant
        for field, value in data.changes().items():
            setattr(tenant, field, value)
        self.db.commit()
        return tenant

    def get_settings(self) -> InstituteSettings:
        return self.settings.current()

    def update_settings(self, data: SettingsUpdate) -> InstituteSettings:
        settings = self.settings.current()
        for field, value in data.changes().items():
            setattr(settings, field, value)
        self.db.commit()
        return settings

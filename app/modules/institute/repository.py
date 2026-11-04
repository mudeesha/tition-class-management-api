from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.common.repository import TenantScopedRepository
from app.core.exceptions import NotFound
from app.modules.institute.models import Counter, InstituteSettings

if TYPE_CHECKING:
    from app.tenancy.context import TenantContext


class InstituteSettingsRepository(TenantScopedRepository[InstituteSettings]):
    model = InstituteSettings

    def current(self) -> InstituteSettings:
        settings = self.first()
        if settings is None:
            raise NotFound("Institute settings are missing")
        return settings


class CounterRepository:
    """Hands out the next number for a key. Safe when two requests ask at the same time:
    the row is locked by the upsert until the transaction ends."""

    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx

    def next(self, key: str) -> int:
        stmt = (
            insert(Counter)
            .values(tenant_id=self.ctx.tenant_id, key=key, last_value=1)
            .on_conflict_do_update(
                index_elements=[Counter.tenant_id, Counter.key],
                set_={"last_value": Counter.last_value + 1},
            )
            .returning(Counter.last_value)
        )
        return self.db.execute(stmt).scalar_one()

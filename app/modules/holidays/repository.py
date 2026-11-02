import datetime as dt

from sqlalchemy import Select, or_

from app.common.repository import TenantScopedRepository
from app.modules.holidays.models import Holiday


class HolidayRepository(TenantScopedRepository[Holiday]):
    """Shows all-branch holidays plus those of the branches the member can work in."""

    model = Holiday
    label = "Holiday"

    def query(self) -> Select[tuple[Holiday]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(
                or_(Holiday.branch_id.is_(None), Holiday.branch_id.in_(self.ctx.branch_ids))
            )
        return stmt

    def taken(self, day: dt.date, branch_id: int | None, exclude_id: int | None = None) -> bool:
        stmt = (
            super()
            .query()
            .where(
                Holiday.date == day,
                Holiday.branch_id.is_(None)
                if branch_id is None
                else Holiday.branch_id == branch_id,
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(Holiday.id != exclude_id)
        return self.db.scalars(stmt.limit(1)).first() is not None

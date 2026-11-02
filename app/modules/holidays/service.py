from __future__ import annotations

import datetime as dt

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden
from app.modules.branches.repository import BranchRepository
from app.modules.holidays.models import Holiday
from app.modules.holidays.repository import HolidayRepository
from app.modules.holidays.schemas import HolidayCreate, HolidayUpdate
from app.tenancy.context import TenantContext


class HolidayService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.holidays = HolidayRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)

    def list(
        self,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        branch_id: int | None = None,
    ) -> list[Holiday]:
        """With branch_id: that branch's holidays plus the all-branch ones."""
        where = []
        if date_from:
            where.append(Holiday.date >= date_from)
        if date_to:
            where.append(Holiday.date <= date_to)
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
            where.append(or_(Holiday.branch_id.is_(None), Holiday.branch_id == branch_id))
        return self.holidays.find(*where, order_by=[Holiday.date])

    def get(self, holiday_id: int) -> Holiday:
        return self.holidays.get_or_404(holiday_id)

    def create(self, data: HolidayCreate) -> Holiday:
        self._check_branch(data.branch_id)
        if self.holidays.taken(data.date, data.branch_id):
            raise Conflict(f"There is already a holiday on {data.date}")
        holiday = self.holidays.add(Holiday(**data.model_dump()))
        self.db.commit()
        return holiday

    def update(self, holiday_id: int, data: HolidayUpdate) -> Holiday:
        holiday = self.get(holiday_id)
        self._check_branch(holiday.branch_id)
        changes = data.changes()
        day = changes.get("date", holiday.date)
        branch_id = changes.get("branch_id", holiday.branch_id)
        if "branch_id" in changes:
            self._check_branch(branch_id)
        if self.holidays.taken(day, branch_id, holiday.id):
            raise Conflict(f"There is already a holiday on {day}")
        for field, value in changes.items():
            setattr(holiday, field, value)
        self.db.commit()
        return holiday

    def delete(self, holiday_id: int) -> None:
        holiday = self.get(holiday_id)
        self._check_branch(holiday.branch_id)
        self.holidays.delete(holiday)
        self.db.commit()

    def _check_branch(self, branch_id: int | None) -> None:
        """All-branch holidays need all-branch access; others need access to that branch."""
        if branch_id is None:
            if not self.ctx.all_branches:
                raise Forbidden("Only members with access to all branches can set these holidays")
        else:
            self.branches.get_or_404(branch_id)

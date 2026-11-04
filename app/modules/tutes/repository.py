import datetime as dt

from sqlalchemy import Select, exists, func, select

from app.common.repository import TenantScopedRepository
from app.modules.classes.models import TuitionClass
from app.modules.tutes.models import Tute, TuteIssue, tute_classes


class TuteRepository(TenantScopedRepository[Tute]):
    """Members limited to some branches see tutes used by a class in one of them."""

    model = Tute
    label = "Tute"

    def query(self) -> Select[tuple[Tute]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(
                exists()
                .where(tute_classes.c.tute_id == Tute.id)
                .where(tute_classes.c.class_id == TuitionClass.id)
                .where(TuitionClass.branch_id.in_(self.ctx.branch_ids))
            )
        return stmt

    def search(
        self,
        q: str | None,
        month: dt.date | None,
        class_id: int | None,
        teacher_id: int | None,
    ) -> Select[tuple[Tute]]:
        stmt = self.query()
        if q:
            stmt = stmt.where(func.lower(Tute.title).like(f"%{q.lower()}%"))
        if month is not None:
            stmt = stmt.where(Tute.month == month)
        if class_id is not None:
            stmt = stmt.where(self._used_by([class_id]))
        if teacher_id is not None:
            stmt = stmt.where(Tute.teacher_id == teacher_id)
        return stmt.order_by(Tute.month.desc(), Tute.number.desc().nulls_last(), Tute.id.desc())

    def for_classes(self, class_ids: list[int]) -> list[Tute]:
        if not class_ids:
            return []
        return self.find(self._used_by(class_ids), order_by=[Tute.month.desc(), Tute.id.desc()])

    @staticmethod
    def _used_by(class_ids: list[int]):
        return exists().where(
            tute_classes.c.tute_id == Tute.id, tute_classes.c.class_id.in_(class_ids)
        )


class TuteIssueRepository(TenantScopedRepository[TuteIssue]):
    model = TuteIssue
    label = "Hard copy"

    def for_tute(self, tute_id: int) -> dict[int, TuteIssue]:
        return {i.student_id: i for i in self.find(TuteIssue.tute_id == tute_id)}

    def for_student(self, student_id: int) -> set[int]:
        stmt = select(TuteIssue.tute_id).where(
            TuteIssue.tenant_id == self.ctx.tenant_id, TuteIssue.student_id == student_id
        )
        return set(self.db.scalars(stmt))

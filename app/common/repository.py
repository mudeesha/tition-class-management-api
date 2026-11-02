"""Base repositories. All SELECT queries live in repositories; services own commits.

TenantScopedRepository adds `tenant_id = <current institute>` to every query, and
BranchScopedRepository also limits rows to the branches the current member can work in.
Building tenant queries any other way risks showing one institute's data to another.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound

if TYPE_CHECKING:
    from app.tenancy.context import TenantContext


class Repository[M]:
    model: type[M]
    label: str | None = None  # used in "X not found" messages

    def __init__(self, db: Session) -> None:
        self.db = db

    def query(self) -> Select[tuple[M]]:
        return select(self.model)

    def get(self, id: int) -> M | None:
        return self.db.scalar(self.query().where(self.model.id == id))  # type: ignore[attr-defined]

    def get_or_404(self, id: int) -> M:
        obj = self.get(id)
        if obj is None:
            raise NotFound(f"{self.label or self.model.__name__} not found")
        return obj

    def find(self, *where: ColumnElement[bool], order_by: Sequence[Any] = ()) -> list[M]:
        return list(self.db.scalars(self.query().where(*where).order_by(*order_by)))

    def first(self, *where: ColumnElement[bool]) -> M | None:
        return self.db.scalars(self.query().where(*where).limit(1)).first()

    def exists(self, *where: ColumnElement[bool]) -> bool:
        return self.first(*where) is not None

    def count(self, *where: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(self.query().where(*where).subquery())
        return self.db.scalar(stmt) or 0

    def paginate(self, stmt: Select[tuple[M]], page: int, size: int) -> tuple[list[M], int]:
        total = self.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        items = self.db.scalars(stmt.limit(size).offset((page - 1) * size)).unique()
        return list(items), total or 0

    def add(self, obj: M) -> M:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: M) -> None:
        self.db.delete(obj)
        self.db.flush()


class TenantScopedRepository[M](Repository[M]):
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        super().__init__(db)
        self.ctx = ctx

    def query(self) -> Select[tuple[M]]:
        return super().query().where(self.model.tenant_id == self.ctx.tenant_id)  # type: ignore[attr-defined]

    def add(self, obj: M) -> M:
        obj.tenant_id = self.ctx.tenant_id  # type: ignore[attr-defined]
        return super().add(obj)


class BranchScopedRepository[M](TenantScopedRepository[M]):
    """For tables with a required branch_id."""

    def query(self) -> Select[tuple[M]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(self.model.branch_id.in_(self.ctx.branch_ids))  # type: ignore[attr-defined]
        return stmt

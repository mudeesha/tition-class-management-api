from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from fastapi import Depends
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    MetaData,
    Numeric,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings

# Stable constraint names, so Alembic migrations stay predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        int: BigInteger,
        Decimal: Numeric(12, 2),
        datetime: DateTime(timezone=True),
    }


class IdMixin:
    id: Mapped[int] = mapped_column(Identity(), primary_key=True, sort_order=-10)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=10)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), sort_order=10
    )


class TenantMixin:
    """Every institute-owned table. Always filtered by TenantScopedRepository."""

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, sort_order=-5
    )


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store enums as plain strings (their values), so adding a value needs no DB enum change."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=30,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, event, false, inspect
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    selectinload,
    with_loader_criteria,
)
from sqlalchemy.orm.relationships import RelationshipProperty
from sqlalchemy.sql import Select


class Base(DeclarativeBase):
    pass


_INVALID = object()


def _coerce(column: Column, raw_value: str) -> Any:
    """Turn a raw query-string value into something comparable to `column`. Only bool/int need
    real coercion — a plain string column compares fine against another string as-is.
    """
    python_type = column.type.python_type
    if python_type is bool:
        if raw_value.lower() in ("true", "1"):
            return True
        if raw_value.lower() in ("false", "0"):
            return False
        return _INVALID
    if python_type is int:
        try:
            return int(raw_value)
        except ValueError:
            return _INVALID
    return raw_value


class Queryable:
    """Mix into any model for allow-listed filtering/sorting/including over its real columns and
    relationships — same inherit-and-go shape as SoftDeleteMixin, no per-model service registry
    needed.

    Filterable/sortable fields are every real column minus `__hidden__` (this model's own
    equivalent of Eloquent's `$hidden` — SQLAlchemy has no built-in concept of this, so it's a
    convention we own, same as SoftDeleteMixin owns `deleted_at`). `__default_sort__` is the
    same idea for ordering — SQLAlchemy 2.0 dropped the legacy `Mapper(order_by=...)` argument
    (a 1.x feature; 2.0 wants ordering explicit at the query site), so this is our own
    equivalent rather than a native mapper option. `__includable__` is the opposite of
    `__hidden__` — an allow-list, not a deny-list — since eager-loading an arbitrary relationship
    is a much bigger blast radius (whole related tables, not a single column) than filtering on
    one:

        class User(Queryable, SoftDeleteMixin, Base):
            __hidden__ = {"password"}
            __default_sort__ = "id"
            __includable__ = {"categories"}
    """

    __hidden__: set[str] = set()
    __default_sort__: str | None = None
    __includable__: set[str] = set()

    @classmethod
    def _queryable_columns(cls) -> dict[str, Column]:
        return {
            name: column
            for name, column in inspect(cls).mapper.columns.items()
            if name not in cls.__hidden__
        }

    @classmethod
    def _includable_relationships(cls) -> dict[str, RelationshipProperty]:
        return {
            name: relationship
            for name, relationship in inspect(cls).mapper.relationships.items()
            if name in cls.__includable__
        }

    @classmethod
    def apply_filters(cls, stmt: Select, filters: dict[str, str]) -> Select:
        columns = cls._queryable_columns()
        for field, raw_value in filters.items():
            column = columns.get(field)
            if column is None:
                continue  # unknown or hidden field — ignored, not a query error
            value = _coerce(column, raw_value)
            if value is _INVALID:
                return stmt.where(false())  # bad input on a real column -> zero rows, not a 500
            stmt = stmt.where(column == value)
        return stmt

    @classmethod
    def _resolve_sort(cls, sort: str | None) -> tuple[Column | None, bool]:
        """Turns a `sort=`/`sort=-field` string (or `__default_sort__` when None) into the actual
        column plus direction — shared by `apply_sort` and cursor pagination, which needs the same
        resolution to build its keyset comparison.
        """
        sort = sort or cls.__default_sort__
        if not sort:
            return None, False
        descending = sort.startswith("-")
        column = cls._queryable_columns().get(sort[1:] if descending else sort)
        return column, descending

    @classmethod
    def apply_sort(cls, stmt: Select, sort: str | None) -> Select:
        column, descending = cls._resolve_sort(sort)
        if column is None:
            return stmt
        return stmt.order_by(column.desc() if descending else column.asc())

    @classmethod
    def apply_includes(cls, stmt: Select, includes: list[str]) -> Select:
        """Eager-loads each requested relation via selectinload — a separate batched `IN (...)`
        query per relation, run once for the whole page rather than once per row. This is the
        actual N+1 prevention: a relationship named here is always loaded this way, so accessing
        it during serialization never falls back to per-row lazy loading.
        """
        relationships = cls._includable_relationships()
        for alias in includes:
            relationship = relationships.get(alias)
            if relationship is None:
                continue  # unknown or not allow-listed — ignored, not a query error
            stmt = stmt.options(selectinload(getattr(cls, alias)))
        return stmt


@dataclass
class QB:
    """What a listing endpoint needs to build its query — filters, sort, includes, and the model
    they apply to — bundled together so a route can pass this straight through to its service
    function, and the service applies everything in one call via `qb.apply(select(Model))`. Same
    shape as a Laravel model's `getQB()`: one object, one call, fully configured. Lives here, not
    in app/api/deps.py, so services can depend on it without an api -> service -> api import cycle.
    """

    model: type[Queryable]
    filters: dict[str, str]
    sort: str | None
    include: list[str]

    def apply(self, stmt: Select) -> Select:
        stmt = self.model.apply_filters(stmt, self.filters)
        stmt = self.model.apply_sort(stmt, self.sort)
        return self.model.apply_includes(stmt, self.include)


class SoftDeleteMixin:
    """Mix into any model to get Laravel's SoftDeletes trait: add this, run a migration for the
    column, and every query excludes deleted rows automatically — no per-query filter to remember,
    anywhere, ever. See the do_orm_execute listener below for how that's enforced.

    Need a trashed row anyway (a future restore feature, an admin view)? Opt out per-query:
        db.scalars(select(User).execution_options(include_deleted=True))
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@event.listens_for(Session, "do_orm_execute")
def _exclude_soft_deleted(execute_state) -> None:
    """Global scope, SQLAlchemy-style: inject `deleted_at IS NULL` into every SELECT touching a
    SoftDeleteMixin model — covers select()/scalars() queries and Session.get() alike.
    """
    if execute_state.is_select and not execute_state.execution_options.get("include_deleted", False):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )


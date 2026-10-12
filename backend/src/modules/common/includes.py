"""Support for ``?include=<relationship>`` on list endpoints.

How a developer makes a relationship includable:

1. On the model, declare the relationship and list its name in ``__includable__``::

       class User(Base):
           __includable__ = {"products"}
           products: Mapped[list["Product"]] = relationship(...)

2. On the Read schema, add an optional field with the same name::

       products: list[ProductRead] | None = None

3. In the list route, use ``include_param(Model)`` and ``attach_includes(...)``, and set
   ``response_model_exclude_unset=True`` so the key is left out when it was not requested.

Only direct foreign-key relationships (one-to-many, many-to-one) are supported.
Many-to-many relationships (``secondary=``) are not.
"""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import Query
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession


def include_param(model: Any) -> Callable[..., list[str]]:
    """Build a FastAPI dependency that reads ``?include=a,b`` into ``["a", "b"]``.

    The model's allowed names are written into the parameter description, so /docs
    always shows what can be included.
    """
    allowed = ", ".join(sorted(getattr(model, "__includable__", set()))) or "(none)"

    def dependency(
        include: str | None = Query(default=None, description=f"Comma-separated relations to include: {allowed}"),
    ) -> list[str]:
        return [name.strip() for name in include.split(",") if name.strip()] if include else []

    return dependency


async def attach_includes(
    db: AsyncSession, model: Any, rows: list[dict[str, Any]], includes: list[str]
) -> list[dict[str, Any]]:
    """Add each requested relationship to every row, using one query per relationship.

    Names that are not in ``model.__includable__`` (or are not real relationships) are
    ignored. Names that were not requested are never added, so those keys stay absent.
    """
    relationships = inspect(model).relationships
    allowed: set[str] = getattr(model, "__includable__", set())

    for name in includes:
        if name not in allowed or name not in relationships:
            continue

        relationship = relationships[name]
        related_model = relationship.mapper.class_
        # The two columns that join the tables, e.g. user.id (local) and product.owner_id (remote).
        local_column, remote_column = relationship.local_remote_pairs[0]

        # One query for all rows: SELECT ... FROM product WHERE owner_id IN (<all user ids>)
        query = select(related_model).where(remote_column.in_({row[local_column.key] for row in rows}))
        if hasattr(related_model, "is_deleted"):
            query = query.where(related_model.is_deleted.is_(False))

        # Group the related rows by the id of the row they belong to.
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for related in await db.scalars(query):
            grouped[getattr(related, remote_column.key)].append(
                {column.key: getattr(related, column.key) for column in relationship.mapper.column_attrs}
            )

        for row in rows:
            items = grouped.get(row[local_column.key], [])
            row[name] = items if relationship.uselist else (items[0] if items else None)

    return rows

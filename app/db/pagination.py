import base64
import json
from collections.abc import Callable
from typing import Any

from fastapi import Request
from sqlalchemy import Column, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.config import get_settings
from app.db.base import QB
from app.schemas.common import PaginatedResponse

settings = get_settings()


def paginate(
    db: Session, base_stmt: Select, request: Request, qb: QB, mapper: Callable[[Any], Any]
) -> PaginatedResponse[Any]:
    """Runs `base_stmt` (filters/includes/sort from `qb` applied here, not by the caller) and
    returns the fully-built response envelope — the one place every listing endpoint gets
    pagination from. A service just returns this directly instead of reconstructing the envelope
    by hand.

    Two modes, chosen by what the request sends — see `PaginatedResponse`'s docstring for the
    tradeoff each one makes:

    - No `cursor` param (the default): offset/limit pagination, `?page=`/`?per_page=`.
    - `cursor` param present: keyset pagination, `?cursor=`/`?direction=`&`?per_page=` — the fix
      for deep `OFFSET` pages costing more the further in you go. `base_stmt` can't come
      pre-sorted for this mode (unlike offset mode) — cursor pagination needs to control the
      ORDER BY itself to keep it consistent with the keyset comparison, so `qb.apply_sort` is
      applied inside here, per mode, not by the caller.

    `mapper` (e.g. `to_user_read`) is a required, explicit argument rather than something
    paginate() derives on its own — the conversion isn't a plain attribute passthrough Pydantic
    could do automatically: a profile picture's URL is a presigned URL computed on the fly (the
    ORM object has no `url` attribute to read), and `categories`/`user` are only populated when
    the caller actually eager-loaded them (checked via `inspect(row).unloaded`), which is what
    keeps this N+1-safe. That's real logic, not boilerplate, so it stays a real function.

    `per_page == -1` ("give me everything," a Laravel `paginate($limit) unless limit == -1, then
    get()` convention) is clamped to `settings.pagination_max_limit`, not actually unbounded — at
    a million-row table, no limit at all means loading every row into memory, building a response
    object for each one, and running the mapper on all of them synchronously in one request.
    """
    stmt = qb.model.apply_filters(base_stmt, qb.filters)
    stmt = qb.model.apply_includes(stmt, qb.include)

    per_page = _int_param(request, "per_page", default=settings.pagination_limit)
    if per_page == -1:
        per_page = settings.pagination_max_limit

    if request.query_params.get("cursor") is not None or request.query_params.get("direction") is not None:
        return _cursor_paginate(db, stmt, request, qb, mapper, per_page)
    return _offset_paginate(db, stmt, request, qb, mapper, per_page)


def _offset_paginate(
    db: Session, stmt: Select, request: Request, qb: QB, mapper: Callable[[Any], Any], per_page: int
) -> PaginatedResponse[Any]:
    """No `COUNT(*)` — the only thing it would be for is `total`/`last_page`, which
    `PaginatedResponse` doesn't carry. Instead this fetches one row past `per_page`: getting it
    back means there's a next page, and it's trimmed before returning. That costs the same at 100
    rows or 100 million — no query whose cost scales with table size (unlike the `OFFSET` itself
    on a very deep page, which `_cursor_paginate` exists to avoid).
    """
    stmt = qb.model.apply_sort(stmt, qb.sort)
    page = _int_param(request, "page", default=1)
    offset = (page - 1) * per_page
    rows = list(db.scalars(stmt.offset(offset).limit(per_page + 1)))
    has_next = len(rows) > per_page
    rows = rows[:per_page]

    return PaginatedResponse(
        data=[mapper(row) for row in rows],
        current_page=page,
        per_page=per_page,
        next_page_url=_page_url(request, page=page + 1) if has_next else None,
        prev_page_url=_page_url(request, page=page - 1) if page > 1 else None,
    )


def _cursor_paginate(
    db: Session, stmt: Select, request: Request, qb: QB, mapper: Callable[[Any], Any], per_page: int
) -> PaginatedResponse[Any]:
    """Keyset pagination: `WHERE (sort_column, id) > (cursor_sort_value, cursor_id)` instead of
    `OFFSET n` — the database seeks straight to the right spot via the index instead of scanning
    and discarding everything before it, so page 50,000 costs the same as page 1. `id` is always
    part of the comparison, not just the sort column, because the sort column usually isn't
    unique (`name`, `created_at`, …) — without `id` breaking ties, rows sharing a sort value could
    be skipped or repeated across pages.

    `direction="prev"` is answered by reversing the comparison *and* the ORDER BY, fetching that
    way, then reversing the result back to natural order — the standard trick for keyset
    pagination to support going backwards at all, since there's no `OFFSET -n`.
    """
    sort_column, descending = qb.model._resolve_sort(qb.sort)
    id_column = qb.model._queryable_columns()["id"]
    order_columns = [id_column] if sort_column is None or sort_column.name == "id" else [sort_column, id_column]

    raw_cursor = request.query_params.get("cursor")
    direction = request.query_params.get("direction") or "next"
    cursor_values = _decode_cursor(raw_cursor) if raw_cursor else None

    going_backward = cursor_values is not None and direction == "prev"
    # "Greater than" continues forward through an ascending list, or rewinds backward through a
    # descending one; "less than" is forward through descending or backward through ascending —
    # i.e. greater-than exactly when descending and going_backward agree (both true or both false).
    want_greater_than = descending == going_backward
    query_descending = (not descending) if going_backward else descending

    if cursor_values is not None:
        cursor_tuple = tuple_(*order_columns)
        stmt = stmt.where(cursor_tuple > tuple_(*cursor_values) if want_greater_than else cursor_tuple < tuple_(*cursor_values))

    stmt = stmt.order_by(*(c.desc() if query_descending else c.asc() for c in order_columns))
    fetched = list(db.scalars(stmt.limit(per_page + 1)))
    has_more = len(fetched) > per_page
    fetched = fetched[:per_page]
    rows = list(reversed(fetched)) if going_backward else fetched

    if not rows:
        return PaginatedResponse(data=[], per_page=per_page)

    # Going backward always has a valid "next" (the position we came from); going forward only
    # has one if the +1 probe row came back. Symmetrically for "prev": going forward always has a
    # valid "prev" once any cursor was supplied; going backward only has one if the probe row did.
    has_next = going_backward or has_more
    has_prev = (not going_backward and cursor_values is not None) or (going_backward and has_more)
    next_cursor = _encode_cursor(rows[-1], order_columns) if has_next else None
    prev_cursor = _encode_cursor(rows[0], order_columns) if has_prev else None

    return PaginatedResponse(
        data=[mapper(row) for row in rows],
        per_page=per_page,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        next_page_url=_cursor_url(request, next_cursor, "next") if next_cursor else None,
        prev_page_url=_cursor_url(request, prev_cursor, "prev") if prev_cursor else None,
    )


def _encode_cursor(row: Any, order_columns: list[Column]) -> str:
    values = [_jsonable(getattr(row, column.name)) for column in order_columns]
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode()


def _decode_cursor(cursor: str) -> list[Any]:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


def _jsonable(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _page_url(request: Request, page: int) -> str:
    return str(request.url.include_query_params(page=page))


def _cursor_url(request: Request, cursor: str, direction: str) -> str:
    return str(request.url.include_query_params(cursor=cursor, direction=direction))

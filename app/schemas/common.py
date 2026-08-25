from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Shared envelope for every paginated listing endpoint — covers both pagination modes
    `paginate()` supports. No `total`/`last_page` in either mode — that's Laravel's
    `simplePaginate()` shape, not `paginate()`'s: computing an exact total means a `COUNT(*)` on
    every request, which gets slower as a table grows and has no index-only shortcut on Postgres.

    Offset mode (`?page=`, the default): `current_page`/`next_page_url`/`prev_page_url` populated,
    `next_cursor`/`prev_cursor` are `None`. Costs the same per page regardless of table size, but
    `page=50000` still means the DB scans and discards ~750K rows first — fine at this project's
    scale, degrades on very large tables.

    Cursor mode (`?cursor=`, opt-in): `next_cursor`/`prev_cursor` populated (and mirrored into
    `next_page_url`/`prev_page_url` as ready-to-follow URLs), `current_page` is `None` — a cursor
    isn't a page number, it's "resume right after this row." Same cost at page 1 or page 50,000,
    the tradeoff Laravel's own `cursorPaginate()` makes for the same reason.
    """

    data: list[T]
    per_page: int
    current_page: int | None = None
    next_page_url: str | None = None
    prev_page_url: str | None = None
    next_cursor: str | None = None
    prev_cursor: str | None = None

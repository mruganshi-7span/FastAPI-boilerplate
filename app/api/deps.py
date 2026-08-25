import inspect as _inspect
from collections.abc import Callable, Generator
from typing import Any

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.db.base import QB, Queryable
from app.db.session import SessionLocal
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_qb(model: type[Queryable]) -> Callable[..., QB]:
    """Builds one dependency exposing everything a listing endpoint needs — `filter[field]=` for
    every real, non-hidden column of `model`, plus `sort=` and `include=` — straight from the
    model's own Queryable allow-lists. Mirrors a Laravel model's `getQB()`: one factory call, no
    per-resource filter/include function to write or keep in sync, no route code to touch when a
    column or relationship is added. Still fully docs-friendly — FastAPI reads the generated
    signature exactly like a hand-written one, so every field shows up individually in the
    OpenAPI schema.
    """
    fields = list(model._queryable_columns().keys())
    includable = sorted(model.__includable__)

    def dependency(**kwargs: Any) -> QB:
        sort = kwargs.pop("sort")
        raw_include = kwargs.pop("include")
        include = [alias.strip() for alias in raw_include.split(",")] if raw_include else []
        filters = {field: value for field, value in kwargs.items() if value is not None}
        return QB(model=model, filters=filters, sort=sort, include=include)

    dependency.__signature__ = _inspect.Signature(
        [
            _inspect.Parameter(
                "sort",
                _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Query(default=None, description="Field to sort by, `-` prefix for descending"),
                annotation=str | None,
            ),
            _inspect.Parameter(
                "include",
                _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Query(
                    default=None,
                    description=f"Comma-separated relations to eager-load: {', '.join(includable) or '(none)'}",
                ),
                annotation=str | None,
            ),
            *[
                _inspect.Parameter(
                    field,
                    _inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=Query(default=None, alias=f"filter[{field}]"),
                    annotation=str | None,
                )
                for field in fields
            ],
        ]
    )
    return dependency


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedException()

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise UnauthorizedException("auth.token_invalid")

    user_id = payload.get("sub")
    user = db.get(User, int(user_id)) if user_id is not None else None
    if user is None:
        raise UnauthorizedException("auth.user_no_longer_exists")

    if not user.is_active:
        raise UnauthorizedException("auth.account_deactivated")

    return user

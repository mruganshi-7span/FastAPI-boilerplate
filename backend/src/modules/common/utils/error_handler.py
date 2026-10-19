"""Utility functions for mapping exceptions to HTTP error responses.

Every error the API returns has the same body::

    {"message": "<text>", "errors": {"<field>": ["<text>", ...]}}

``errors`` is only present when there are field-level problems to report.
"""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ....infrastructure.auth.http_exceptions import (
    HTTPException,
)
from ....infrastructure.logging import get_logger
from ..constants import EXCEPTION_MAPPING, GENERIC_ERROR_MESSAGE, VALIDATION_ERROR_MESSAGE
from ..exceptions import DomainError

logger = get_logger()

# Statuses that must not carry a body.
_BODYLESS_STATUS_CODES = {204, 304}


def error_response(
    status_code: int,
    message: str,
    errors: Mapping[str, list[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build the standard error response: ``{"message", "errors"?}``."""
    body: dict[str, object] = {"message": message}
    if errors:
        body["errors"] = dict(errors)
    return JSONResponse(status_code=status_code, content=body, headers=dict(headers) if headers else None)


def map_exception(error: DomainError) -> HTTPException:
    """Map a domain exception to a corresponding HTTP exception.

    Walks the exception's MRO and uses the first exact-type match found in
    EXCEPTION_MAPPING, so the most specific mapping wins regardless of the
    order entries appear in the mapping.
    """
    for exception_class in type(error).__mro__:
        mapper = EXCEPTION_MAPPING.get(exception_class)
        if mapper is not None:
            return mapper(str(error))

    logger.error(f"Unmapped domain error: {type(error).__name__}: {error}")
    return HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE)


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a generic 500."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
            return error_response(500, GENERIC_ERROR_MESSAGE)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers.

    Every response has the shape ``{"message", "errors"?}``. Details are logged
    server-side. The client gets the message ``EXCEPTION_MAPPING`` defines for a
    ``DomainError`` - never the raw domain message, which can name rows the caller
    isn't entitled to know about - plus the ``errors`` the service chose to expose.
    InvalidMediaError (422) passes its own message, since the frontend needs it.
    """
    app.add_middleware(CatchAllErrorMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, list[str]] = {}
        for error in exc.errors():
            # loc[0] is where the value came from (body, query, ...); the rest is the field path.
            field = ".".join(str(part) for part in error["loc"][1:]) or "body"
            errors.setdefault(field, []).append(error["msg"])

        logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
        return error_response(422, VALIDATION_ERROR_MESSAGE, errors)

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        http_exception = map_exception(exc)

        logger.warning(f"Domain error on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
        return error_response(http_exception.status_code, str(http_exception.detail), exc.errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
        # Covers FastAPI/fastcrud HTTPExceptions (auth, CSRF, permissions) and Starlette's own 404/405.
        log = logger.error if exc.status_code >= 500 else logger.warning
        log(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")

        if exc.status_code in _BODYLESS_STATUS_CODES:
            return Response(status_code=exc.status_code, headers=exc.headers)
        return error_response(exc.status_code, str(exc.detail), headers=exc.headers)


def handle_exception(error: Exception) -> HTTPException | None:
    """Handle an exception and return an appropriate HTTP exception if possible.

    For use in route handlers when you want to handle exceptions manually.
    """
    if isinstance(error, DomainError):
        return map_exception(error)
    elif isinstance(error, HTTPException):
        return error
    return None

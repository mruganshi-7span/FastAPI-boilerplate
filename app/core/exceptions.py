import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.localization import request_locale, translate

logger = logging.getLogger(__name__)

# A field error is either a plain translation key, or (key, params) when the message needs
# interpolation — e.g. ("mediable.target_not_found", {"type": "user"}).
FieldError = str | tuple[str, dict[str, object]]


class AppException(Exception):
    """Carries a translation key, not translated text — translation happens once, in the handler
    below, where a `request` (and therefore a resolved locale) is actually available. Services
    raising these never need to know the current locale at all.
    """

    def __init__(self, key: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.key = key
        self.status_code = status_code
        super().__init__(key)


class NotFoundException(AppException):
    def __init__(self, key: str = "common.not_found") -> None:
        super().__init__(key, status.HTTP_404_NOT_FOUND)


class UnauthorizedException(AppException):
    def __init__(self, key: str = "common.unauthenticated") -> None:
        super().__init__(key, status.HTTP_401_UNAUTHORIZED)


class ValidationException(AppException):
    def __init__(self, key: str = "validation.invalid", errors: dict[str, list[FieldError]] | None = None) -> None:
        self.errors = errors or {}
        super().__init__(key, status.HTTP_422_UNPROCESSABLE_CONTENT)


def _translate_field_errors(errors: dict[str, list[FieldError]], locale: str) -> dict[str, list[str]]:
    translated: dict[str, list[str]] = {}
    for field, items in errors.items():
        translated[field] = [
            translate(item, locale=locale) if isinstance(item, str) else translate(item[0], locale=locale, **item[1])
            for item in items
        ]
    return translated


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        locale = request_locale(request)
        body: dict[str, object] = {"message": translate(exc.key, locale=locale)}
        if isinstance(exc, ValidationException) and exc.errors:
            body["errors"] = _translate_field_errors(exc.errors, locale)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, list[str]] = {}
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"][1:]) or "body"
            errors.setdefault(field, []).append(error["msg"])

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"message": translate("validation.invalid", locale=request_locale(request)), "errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Anything reaching here is a bug or a misconfiguration, not client error — log the full
        # traceback server-side, but never leak it (file paths, library internals) to the client.
        logger.exception("Unhandled exception while processing request", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": translate("common.server_error", locale=request_locale(request))},
        )

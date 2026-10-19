"""Common constants used across the application."""

from collections.abc import Callable

from ...infrastructure.auth.http_exceptions import (
    DuplicateValueException,
    ForbiddenException,
    HTTPException,
    NotFoundException,
    UnprocessableEntityException,
)
from .exceptions import (
    DomainError,
    InvalidMediaError,
    PermissionDeniedError,
    ResourceExistsError,
    ResourceNotFoundError,
    StorageUnavailableError,
    UserExistsError,
    UserNotFoundError,
    ValidationError,
)

# Generic error message for client-facing responses (never leak internal details)
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again."
VALIDATION_ERROR_MESSAGE = "The given data was invalid."

# Safety limits for queries that could be unbounded
MAX_ENTITLEMENTS_PER_USER = 100
DEFAULT_BATCH_SIZE = 100

EXCEPTION_MAPPING: dict[type[DomainError], Callable[[str], HTTPException]] = {
    UserNotFoundError: lambda message: NotFoundException(detail="User not found."),
    ResourceNotFoundError: lambda message: NotFoundException(detail="The requested resource was not found."),
    UserExistsError: lambda message: DuplicateValueException(detail="A user with this email or username already exists."),
    ResourceExistsError: lambda message: DuplicateValueException(detail="This resource already exists."),
    ValidationError: lambda message: UnprocessableEntityException(detail="The request could not be processed."),
    PermissionDeniedError: lambda message: ForbiddenException(detail="You don't have permission for this action."),
    InvalidMediaError: lambda message: UnprocessableEntityException(detail=message or "Invalid media."),
    StorageUnavailableError: lambda message: HTTPException(
        status_code=503, detail="File storage is unavailable. Please try again later."
    ),
}

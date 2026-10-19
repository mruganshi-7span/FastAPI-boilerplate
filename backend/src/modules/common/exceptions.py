"""Domain exception classes for business logic errors."""


class DomainError(Exception):
    """Base class for all domain-specific errors.

    ``message`` is for the logs only; the client gets the message ``EXCEPTION_MAPPING``
    defines for the exception type. ``errors`` is the opt-in exception to that rule:
    a ``{field: [messages]}`` map that is sent to the client as-is, so every string in
    it must be safe to show to any caller.
    """

    def __init__(self, message: str = "", errors: dict[str, list[str]] | None = None) -> None:
        super().__init__(message)
        self.errors: dict[str, list[str]] = errors or {}


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource cannot be found."""

    pass


class ResourceExistsError(DomainError):
    """Raised when attempting to create a resource that already exists."""

    pass


class ValidationError(DomainError):
    """Raised when data validation fails."""

    pass


class PermissionDeniedError(DomainError):
    """Raised when a user attempts an action they don't have permission for."""

    pass


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user cannot be found."""

    pass


class UserExistsError(ResourceExistsError):
    """Raised when attempting to create a user with an existing email or username."""

    pass


class InvalidMediaError(ValidationError):
    """Raised when an upload request or an uploaded file fails media validation.

    Its message is written for the client (unsupported type, file too large,
    nothing uploaded), so it is passed through in the response.
    """

    pass


class StorageUnavailableError(DomainError):
    """Raised when the object store is not configured or can't be reached."""

    pass

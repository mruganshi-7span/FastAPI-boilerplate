"""Exceptions raised by the object storage layer."""


class StorageError(Exception):
    """Raised when the object store can't be reached or rejects a request."""


class StorageNotConfiguredError(StorageError):
    """Raised when a storage call is made but no bucket is configured."""

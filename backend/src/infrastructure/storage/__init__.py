"""Object storage (S3 or S3-compatible) for media uploads."""

from .exceptions import StorageError, StorageNotConfiguredError
from .s3 import ObjectMetadata, S3Storage, storage

__all__ = [
    "ObjectMetadata",
    "S3Storage",
    "StorageError",
    "StorageNotConfiguredError",
    "storage",
]

from enum import StrEnum


class MediaTag(StrEnum):
    """What an upload is for. Each tag maps to a folder and a set of allowed types."""

    PROFILE = "profile"
    DEFAULT = "default"


class MediaContentType(StrEnum):
    """Content types a client may request an upload URL for."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    GIF = "image/gif"
    PDF = "application/pdf"


class MediableType(StrEnum):
    """Entities media can be attached to. Extend this as more models become mediable."""

    USER = "user"

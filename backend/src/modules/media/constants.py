from .enums import MediaContentType, MediaTag

MEDIA_DISK_S3 = "s3"

MEDIA_KEY_MAX_LENGTH = 500
FILE_NAME_MAX_LENGTH = 255
MIME_TYPE_MAX_LENGTH = 100
DISK_MAX_LENGTH = 20
MEDIABLE_TYPE_MAX_LENGTH = 50
TAG_MAX_LENGTH = 50

CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    MediaContentType.JPEG: "jpg",
    MediaContentType.PNG: "png",
    MediaContentType.WEBP: "webp",
    MediaContentType.GIF: "gif",
    MediaContentType.PDF: "pdf",
}

IMAGE_CONTENT_TYPES: frozenset[str] = frozenset(
    {MediaContentType.JPEG, MediaContentType.PNG, MediaContentType.WEBP, MediaContentType.GIF}
)

# Folder each tag's uploads land in. Keys are built as ``{directory}/{owner_id}/{uuid}.{ext}``,
# so an upload can only be confirmed by the user who requested its URL.
TAG_DIRECTORIES: dict[MediaTag, str] = {
    MediaTag.PROFILE: "users/profiles",
    MediaTag.DEFAULT: "default",
}

TAG_CONTENT_TYPES: dict[MediaTag, frozenset[str]] = {
    MediaTag.PROFILE: IMAGE_CONTENT_TYPES,
    MediaTag.DEFAULT: frozenset(CONTENT_TYPE_EXTENSIONS),
}

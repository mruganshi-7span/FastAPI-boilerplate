import uuid
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ValidationException
from app.models.media import Media
from app.schemas.media import MediaConfirmRequest, MediaRead, MediaUploadRequest, MediaUploadUrlResponse
from app.services import storage_service

settings = get_settings()

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
}

# Mirrors the Laravel app's media config `tags`/`directory` maps exactly (same tag names, same
# folder layout) — most of these have no FastAPI model behind them yet, but the config is shared
# ahead of the feature the same way the Laravel config file predates every consumer of it.
_TAG_DIRECTORIES: dict[str, str] = {
    "profile": "users/profiles",
    "default": "default",
}


def create_upload_url(payload: MediaUploadRequest) -> MediaUploadUrlResponse:
    directory = _TAG_DIRECTORIES.get(payload.tag)
    if directory is None:
        raise ValidationException(errors={"tag": ["media.unsupported_tag"]})

    extension = _CONTENT_TYPE_EXTENSIONS[payload.content_type]
    key = f"{directory}/{uuid.uuid4().hex}.{extension}"

    upload_url = storage_service.generate_presigned_upload_url(key=key, content_type=payload.content_type)

    return MediaUploadUrlResponse(
        upload_url=upload_url,
        key=key,
        expires_in=settings.presigned_upload_url_expire_seconds,
    )


def confirm_upload(db: Session, payload: MediaConfirmRequest) -> Media:
    if not _is_known_media_key(payload.key):
        raise ValidationException(errors={"key": ["media.invalid_key"]})

    metadata = storage_service.get_object_metadata(key=payload.key)
    if metadata is None:
        raise ValidationException(errors={"key": ["media.not_uploaded"]})

    media = Media(
        disk="s3",
        key=payload.key,
        file_name=PurePosixPath(payload.key).name,
        mime_type=str(metadata["content_type"]),
        size=int(metadata["size"]),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _is_known_media_key(key: str) -> bool:
    return any(key.startswith(f"{directory}/") for directory in _TAG_DIRECTORIES.values())


def to_media_read(media: Media) -> MediaRead:
    return MediaRead(
        id=media.id,
        file_name=media.file_name,
        mime_type=media.mime_type,
        size=media.size,
        url=storage_service.generate_presigned_download_url(key=media.key),
        created_at=media.created_at,
        updated_at=media.updated_at,
    )

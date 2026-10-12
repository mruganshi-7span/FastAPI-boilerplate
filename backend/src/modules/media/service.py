import asyncio
import re
import uuid
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import get_settings
from ...infrastructure.logging import get_logger
from ...infrastructure.storage import S3Storage, StorageError, storage
from ..common.exceptions import InvalidMediaError, ResourceExistsError, StorageUnavailableError
from .constants import CONTENT_TYPE_EXTENSIONS, TAG_CONTENT_TYPES, TAG_DIRECTORIES
from .crud import crud_media
from .enums import MediableType, MediaTag
from .models import Media, Mediable
from .schemas import MediaRead, MediaUploadRequest

settings = get_settings()
logger = get_logger()

# The part of a key after ``{directory}/{owner_id}/``: a uuid4 hex plus a known extension.
_FILE_NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.(?P<ext>[a-z0-9]+)")


class MediaService:
    """Presigned S3 uploads, confirmed media rows, and polymorphic attachments.

    The upload flow:

    1. ``create_upload_url`` returns a presigned PUT URL and the key it is bound to.
    2. The client PUTs the file to S3 directly.
    3. A feature (e.g. the user profile image) calls ``confirm_upload`` with the key,
       then ``attach`` to link the media to its owner, then commits.
    4. After the commit, ``delete_objects`` removes any files the attach replaced.

    Write methods flush but never commit, so a feature can confirm and attach in
    one transaction; S3 deletes run only after that transaction commits.
    """

    def __init__(self, object_storage: S3Storage = storage) -> None:
        self.storage = object_storage

    @staticmethod
    def owner_prefix(tag: MediaTag, owner_id: int) -> str:
        """The key prefix every upload by ``owner_id`` under ``tag`` starts with."""
        return f"{TAG_DIRECTORIES[tag]}/{owner_id}/"

    async def create_upload_url(self, payload: MediaUploadRequest, owner_id: int) -> dict[str, Any]:
        """Build a fresh key for the owner and presign a PUT for it.

        Args:
            payload: Requested content type and tag.
            owner_id: The user requesting the upload; embedded in the key so only they can confirm it.

        Returns:
            Upload URL, HTTP method, required headers, key and lifetime in seconds.

        Raises:
            InvalidMediaError: If the content type isn't allowed for the tag.
            StorageUnavailableError: If storage isn't configured or can't presign.
        """
        content_type = str(payload.content_type)
        if content_type not in TAG_CONTENT_TYPES[payload.tag]:
            raise InvalidMediaError(f"Content type '{content_type}' is not allowed for tag '{payload.tag}'.")

        extension = CONTENT_TYPE_EXTENSIONS[content_type]
        key = f"{self.owner_prefix(payload.tag, owner_id)}{uuid.uuid4().hex}.{extension}"

        try:
            upload_url = await self.storage.generate_presigned_upload_url(key=key, content_type=content_type)
        except StorageError as exc:
            raise StorageUnavailableError("Could not create an upload URL") from exc

        return {
            "upload_url": upload_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "key": key,
            "expires_in": settings.PRESIGNED_UPLOAD_URL_EXPIRE_SECONDS,
        }

    async def confirm_upload(self, db: AsyncSession, *, key: str, tag: MediaTag, owner_id: int) -> Media:
        """Check an uploaded object in S3 and record it as a media row (flushed, not committed).

        Size and type are read from S3, never trusted from the client. An object
        that is too large or of the wrong type is deleted from the bucket.

        Args:
            db: Database session for the operation.
            key: The key returned by ``create_upload_url``.
            tag: The tag the upload must belong to.
            owner_id: The user confirming; must be the user who requested the URL.

        Returns:
            The new, flushed ``Media`` row.

        Raises:
            InvalidMediaError: If the key isn't the owner's, nothing was uploaded, or the file fails validation.
            ResourceExistsError: If the key was already confirmed.
            StorageUnavailableError: If S3 can't be reached.
        """
        prefix = self.owner_prefix(tag, owner_id)
        match = _FILE_NAME_PATTERN.fullmatch(key[len(prefix) :]) if key.startswith(prefix) else None
        if match is None or match["ext"] not in CONTENT_TYPE_EXTENSIONS.values():
            raise InvalidMediaError("Unknown upload key.")

        if await crud_media.exists(db=db, key=key):
            raise ResourceExistsError(f"Media with key {key} already exists")

        try:
            metadata = await self.storage.get_object_metadata(key=key)
        except StorageError as exc:
            raise StorageUnavailableError("Could not read the uploaded file") from exc

        if metadata is None:
            raise InvalidMediaError("No file was uploaded for this key.")

        allowed_types = TAG_CONTENT_TYPES[tag]
        if metadata.content_type not in allowed_types or CONTENT_TYPE_EXTENSIONS[metadata.content_type] != match["ext"]:
            await self.delete_objects([key])
            raise InvalidMediaError("The uploaded file type is not allowed.")

        if metadata.size <= 0:
            await self.delete_objects([key])
            raise InvalidMediaError("The uploaded file is empty.")

        max_size = settings.MEDIA_MAX_UPLOAD_SIZE_BYTES
        if metadata.size > max_size:
            await self.delete_objects([key])
            raise InvalidMediaError(f"The uploaded file is too large. Maximum size is {max_size} bytes.")

        media = Media(
            key=key,
            file_name=PurePosixPath(key).name,
            mime_type=metadata.content_type,
            size=metadata.size,
        )
        db.add(media)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise ResourceExistsError(f"Media with key {key} already exists") from exc

        return media

    async def attach(
        self,
        db: AsyncSession,
        *,
        media: Media,
        mediable_type: MediableType,
        mediable_id: int,
        tag: MediaTag,
    ) -> list[str]:
        """Attach media to an entity, replacing whatever was attached under the same tag.

        One media per ``(mediable_type, mediable_id, tag)``. Replaced media rows are
        deleted in the same transaction. Flushes but does not commit.

        Returns:
            Keys of replaced files. Pass them to ``delete_objects`` after committing.
        """
        replaced_keys = await self._delete_attachments(
            db, mediable_type=mediable_type, mediable_id=mediable_id, tag=tag, keep_media_id=media.id
        )
        db.add(Mediable(media_id=media.id, mediable_type=mediable_type, mediable_id=mediable_id, tag=tag))
        await db.flush()
        return replaced_keys

    async def detach(
        self,
        db: AsyncSession,
        *,
        mediable_type: MediableType,
        mediable_id: int,
        tag: MediaTag,
    ) -> list[str]:
        """Remove the media attached under a tag, rows included. Flushes but does not commit.

        Returns:
            Keys of removed files. Pass them to ``delete_objects`` after committing.
        """
        removed_keys = await self._delete_attachments(db, mediable_type=mediable_type, mediable_id=mediable_id, tag=tag)
        await db.flush()
        return removed_keys

    async def get_attached(
        self,
        db: AsyncSession,
        *,
        mediable_type: MediableType,
        mediable_ids: Sequence[int],
        tag: MediaTag,
    ) -> dict[int, dict[str, Any]]:
        """Media attached under a tag for many entities at once, with presigned download URLs.

        Returns:
            ``{mediable_id: MediaRead dict}`` for every entity that has media. An entity
            whose URL couldn't be presigned is left out rather than failing the read.
        """
        ids = list(dict.fromkeys(mediable_ids))
        if not ids:
            return {}

        statement = (
            select(Mediable.mediable_id, Media)
            .join(Media, Media.id == Mediable.media_id)
            .where(
                Mediable.mediable_type == mediable_type,
                Mediable.mediable_id.in_(ids),
                Mediable.tag == tag,
            )
            .order_by(Mediable.id)
        )
        rows = (await db.execute(statement)).all()

        # Latest attachment wins if more than one ever slipped in.
        latest: dict[int, Media] = {mediable_id: media for mediable_id, media in rows}
        reads = await asyncio.gather(*(self.to_media_read(media) for media in latest.values()))

        return {mediable_id: read for mediable_id, read in zip(latest, reads, strict=True) if read is not None}

    async def to_media_read(self, media: Media) -> dict[str, Any] | None:
        """Serialize media with a fresh presigned URL, or None if storage can't presign."""
        try:
            url = await self.storage.generate_presigned_download_url(key=media.key)
        except StorageError:
            logger.warning("Could not presign media download URL", extra={"media_id": media.id}, exc_info=True)
            return None

        return MediaRead(
            id=media.id,
            file_name=media.file_name,
            mime_type=media.mime_type,
            size=media.size,
            url=url,
            created_at=media.created_at,
            updated_at=media.updated_at,
        ).model_dump()

    async def delete_objects(self, keys: Sequence[str]) -> None:
        """Best-effort delete of files from S3. Failures are logged, never raised.

        Call only after the transaction that removed their rows has committed, so a
        rollback never leaves a row pointing at a deleted file.
        """
        for key in keys:
            try:
                await self.storage.delete_object(key=key)
            except StorageError:
                logger.warning("Could not delete media object", extra={"key": key}, exc_info=True)

    async def _delete_attachments(
        self,
        db: AsyncSession,
        *,
        mediable_type: MediableType,
        mediable_id: int,
        tag: MediaTag,
        keep_media_id: int | None = None,
    ) -> list[str]:
        statement = (
            select(Mediable, Media)
            .join(Media, Media.id == Mediable.media_id)
            .where(
                Mediable.mediable_type == mediable_type,
                Mediable.mediable_id == mediable_id,
                Mediable.tag == tag,
            )
        )
        rows = (await db.execute(statement)).all()

        removed = [(mediable, media) for mediable, media in rows if media.id != keep_media_id]
        if not removed:
            return []

        # The models have no ORM relationship, so flush the pivot deletes before the
        # media deletes; otherwise the FK cascade could remove pivot rows first.
        for mediable, _ in removed:
            await db.delete(mediable)
        await db.flush()

        for _, media in removed:
            await db.delete(media)

        return [media.key for _, media in removed]

"""Media models: stored files and the polymorphic pivot that attaches them to other rows."""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import (
    DISK_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    MEDIA_DISK_S3,
    MEDIA_KEY_MAX_LENGTH,
    MEDIABLE_TYPE_MAX_LENGTH,
    MIME_TYPE_MAX_LENGTH,
    TAG_MAX_LENGTH,
)


class Media(Base, TimestampMixin):
    """A file stored in object storage.

    Only the key is stored, never a URL: download URLs are presigned on every read.
    Size and MIME type come from S3 when the upload is confirmed, not from the client.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    key: Mapped[str] = mapped_column(String(MEDIA_KEY_MAX_LENGTH), unique=True)
    file_name: Mapped[str] = mapped_column(String(FILE_NAME_MAX_LENGTH))
    mime_type: Mapped[str] = mapped_column(String(MIME_TYPE_MAX_LENGTH))
    size: Mapped[int] = mapped_column(BigInteger)
    disk: Mapped[str] = mapped_column(String(DISK_MAX_LENGTH), default=MEDIA_DISK_S3)

    def __repr__(self) -> str:
        return self.key


class Mediable(Base, TimestampMixin):
    """Attaches a media row to any entity, identified by ``(mediable_type, mediable_id)`` and a tag."""

    __tablename__ = "mediables"
    __table_args__ = (Index("ix_mediables_mediable", "mediable_type", "mediable_id", "tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id", ondelete="CASCADE"), index=True)
    mediable_type: Mapped[str] = mapped_column(String(MEDIABLE_TYPE_MAX_LENGTH))
    mediable_id: Mapped[int] = mapped_column(Integer)
    tag: Mapped[str] = mapped_column(String(TAG_MAX_LENGTH))

    def __repr__(self) -> str:
        return f"{self.mediable_type}:{self.mediable_id}:{self.tag} -> media={self.media_id}"

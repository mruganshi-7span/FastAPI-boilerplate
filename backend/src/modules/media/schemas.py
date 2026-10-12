from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .constants import MEDIA_KEY_MAX_LENGTH
from .enums import MediaContentType, MediaTag


class MediaUploadRequest(BaseModel):
    """Ask for a presigned URL to upload one file straight to S3."""

    model_config = ConfigDict(extra="forbid")

    content_type: Annotated[MediaContentType, Field(examples=["image/png"])]
    tag: Annotated[MediaTag, Field(default=MediaTag.DEFAULT, examples=["profile"])]


class MediaUploadUrlResponse(BaseModel):
    """Where and how to upload. Send the file with ``method`` and ``headers`` before ``expires_in`` runs out."""

    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    key: str
    expires_in: Annotated[int, Field(description="Seconds until upload_url expires")]


class MediaConfirmRequest(BaseModel):
    """Confirm an upload by the key returned with its upload URL."""

    model_config = ConfigDict(extra="forbid")

    key: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MEDIA_KEY_MAX_LENGTH,
            examples=["users/profiles/1/0f8fad5bd9cb469fa165e3e4b38a2c3d.png"],
        ),
    ]


class MediaRead(BaseModel):
    """A stored file with a short-lived download URL."""

    id: int
    file_name: str
    mime_type: str
    size: int
    url: Annotated[str, Field(description="Presigned download URL, regenerated on every read")]
    created_at: datetime
    updated_at: datetime | None = None

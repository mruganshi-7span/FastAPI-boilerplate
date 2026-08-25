from datetime import datetime

from pydantic import BaseModel, Field


class MediaUploadRequest(BaseModel):
    content_type: str = Field(pattern=r"^(image/(jpeg|png|webp|gif)|application/pdf)$")
    # Which folder the upload lands in — see media_service._TAG_FOLDERS for the known set.
    tag: str = Field(min_length=1, max_length=50)


class MediaUploadUrlResponse(BaseModel):
    upload_url: str
    key: str
    expires_in: int


class MediaConfirmRequest(BaseModel):
    key: str


class MediaRead(BaseModel):
    id: int
    file_name: str
    mime_type: str
    size: int
    url: str
    created_at: datetime
    updated_at: datetime

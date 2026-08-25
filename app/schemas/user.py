from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import PaginatedResponse
from app.schemas.media import MediaConfirmRequest, MediaRead


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    is_active: bool = True
    # {"key": "..."} from POST /media/upload-url, after the file has been PUT to S3. Verified via
    # S3 HeadObject and attached as the profile picture server-side — see user_service._set_profile.
    profile: MediaConfirmRequest | None = None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=255)
    is_active: bool | None = None
    profile: MediaConfirmRequest | None = None


class UpdateMeRequest(BaseModel):
    # No `is_active` — a user can't (de)activate their own account through self-service update.
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=255)
    profile: MediaConfirmRequest | None = None


class UserCategoryRead(BaseModel):
    """Slim — used only when nested under UserRead.categories, no `user` back-reference."""

    id: int
    name: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    is_active: bool
    profile: MediaRead | None = None
    # Populated only when ?include=categories was requested and eager-loaded — None otherwise,
    # not an empty list, so a caller can tell "not asked for" apart from "asked for, has none".
    categories: list[UserCategoryRead] | None = None
    created_at: datetime
    updated_at: datetime


UserPage = PaginatedResponse[UserRead]

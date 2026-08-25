from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    user_id: int


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    user_id: int | None = None


class CategoryUser(BaseModel):
    """Slim — used only when nested under CategoryRead.user, no `categories` back-reference."""

    id: int
    name: str
    email: str


class CategoryRead(BaseModel):
    id: int
    name: str
    user_id: int
    # Populated only when ?include=user was requested and eager-loaded — None otherwise, not
    # left out, so a caller can tell "not asked for" apart from some future "user was deleted".
    user: CategoryUser | None = None
    created_at: datetime
    updated_at: datetime


CategoryPage = PaginatedResponse[CategoryRead]

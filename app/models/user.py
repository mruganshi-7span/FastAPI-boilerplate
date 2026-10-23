from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, and_, func
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.db.base import Base, Queryable, SoftDeleteMixin
from app.models.media import Media
from app.models.mediable import MEDIABLE_TYPE_USER, Mediable

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.refresh_token import RefreshToken
    from app.models.social_account import SocialAccount


class User(Queryable, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __hidden__ = {"password"}
    __default_sort__ = "id"
    __includable__ = {"categories"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # NULL for users who only ever signed in through a social provider (see social_auth_service).
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    categories: Mapped[list["Category"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    social_accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    # Polymorphic "morphToMany ... wherePivot('tag', 'profile')" equivalent: mediable_id/mediable_type
    # have no real FK (the pivot can point at any table), so the join side has to be marked foreign()
    # explicitly. Read-only — attaching/detaching goes through mediable_service, not this relationship.
    profile: Mapped[Media | None] = relationship(
        Media,
        secondary=Mediable.__table__,
        primaryjoin=lambda: and_(
            foreign(Mediable.mediable_id) == User.id,
            Mediable.mediable_type == MEDIABLE_TYPE_USER,
            Mediable.tag == "profile",
        ),
        secondaryjoin=lambda: Media.id == foreign(Mediable.media_id),
        viewonly=True,
        uselist=False,
        overlaps="mediables,media",
    )

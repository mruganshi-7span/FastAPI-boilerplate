from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.media import Media

MEDIABLE_TYPE_USER = "user"


class Mediable(Base):
    """Polymorphic pivot attaching a Media row to any entity, tagged by purpose (e.g. 'profile')."""

    __tablename__ = "mediables"
    __table_args__ = (Index("ix_mediables_mediable", "mediable_type", "mediable_id", "tag"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)
    mediable_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mediable_id: Mapped[int] = mapped_column(nullable=False)
    tag: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    media: Mapped["Media"] = relationship(back_populates="mediables")

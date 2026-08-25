from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.mediable import Mediable


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    disk: Mapped[str] = mapped_column(String(50), nullable=False, default="s3")
    key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    mediables: Mapped[list["Mediable"]] = relationship(back_populates="media", cascade="all, delete-orphan")

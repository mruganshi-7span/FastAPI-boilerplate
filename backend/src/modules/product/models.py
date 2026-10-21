from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base
from .constants import NAME_MAX_LENGTH, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS


class Product(Base, TimestampMixin, SoftDeleteMixin):
    """A product created and owned by a user."""

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    price: Mapped[Decimal] = mapped_column(Numeric(PRICE_MAX_DIGITS, PRICE_DECIMAL_PLACES))
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)

    description: Mapped[str | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"{self.name} (owner={self.owner_id})"

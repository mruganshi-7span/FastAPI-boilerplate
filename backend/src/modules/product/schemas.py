from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .constants import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS


class ProductBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH, examples=["Mechanical keyboard"])]
    description: Annotated[
        str | None,
        Field(default=None, max_length=DESCRIPTION_MAX_LENGTH, examples=["Hot-swappable, 75% layout"]),
    ]
    price: Annotated[
        Decimal,
        Field(ge=0, max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES, examples=["49.99"]),
    ]


class ProductCreate(ProductBase):
    """Schema for creating a product. The owner is always the authenticated user."""

    model_config = ConfigDict(extra="forbid")


class ProductCreateInternal(ProductBase):
    """Internal schema for product creation, with the owner set server-side."""

    owner_id: int


class ProductUpdate(BaseModel):
    """Schema for updating a product. Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str | None,
        Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH, examples=["Mechanical keyboard v2"]),
    ]
    description: Annotated[
        str | None,
        Field(default=None, max_length=DESCRIPTION_MAX_LENGTH),
    ]
    price: Annotated[
        Decimal | None,
        Field(default=None, ge=0, max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES, examples=["59.99"]),
    ]


class ProductRead(BaseModel):
    """Schema for reading a product."""

    id: int
    name: str
    description: str | None = None
    price: Decimal
    owner_id: int
    created_at: datetime
    updated_at: datetime | None = None

from typing import Any, cast

from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from .crud import crud_products
from .schemas import ProductCreate, ProductCreateInternal, ProductRead, ProductUpdate

# Columns that cannot be set to NULL, so an explicit null in an update is rejected.
_REQUIRED_FIELDS = ("name", "price")


class ProductService:
    """Service class for product operations.

    Products belong to the user who created them. Any signed-in user can create
    products and read active ones; only the owner (or a superuser) can change or
    delete a product. Deletion is soft.
    """

    async def create(self, payload: ProductCreate, owner_id: int, db: AsyncSession) -> dict[str, Any]:
        """Create a product owned by ``owner_id``.

        Args:
            payload: Product fields from the client.
            owner_id: The authenticated user who will own the product.
            db: Database session for the operation.

        Returns:
            The created product.

        Raises:
            RuntimeError: If the row isn't returned after insert.
        """
        product_internal = ProductCreateInternal(**payload.model_dump(), owner_id=owner_id)
        created = await crud_products.create(db=db, object=product_internal, schema_to_select=ProductRead)
        if not created:
            raise RuntimeError("Product row was not returned after insert")
        return created

    async def get(self, product_id: int, db: AsyncSession) -> dict[str, Any]:
        """Get an active product by id.

        Raises:
            ResourceNotFoundError: If the product doesn't exist or was deleted.
        """
        product = await crud_products.get(db=db, schema_to_select=ProductRead, id=product_id, is_deleted=False)
        if not product:
            raise ResourceNotFoundError(f"Product with ID {product_id} not found")
        return product

    async def get_paginated(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 10,
        owner_id: int | None = None,
    ) -> GetMultiResponseDict:
        """List active products, newest first, optionally only those of one owner."""
        filters: dict[str, Any] = {"is_deleted": False}
        if owner_id is not None:
            filters["owner_id"] = owner_id

        products = await crud_products.get_multi(
            db=db,
            offset=skip,
            limit=limit,
            schema_to_select=ProductRead,
            sort_columns="created_at",
            sort_orders="desc",
            **filters,
        )
        return cast(GetMultiResponseDict, products)

    async def update(
        self,
        product_id: int,
        values: ProductUpdate,
        current_user: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Update a product the current user owns (or any product, for a superuser).

        Raises:
            ResourceNotFoundError: If the product doesn't exist.
            PermissionDeniedError: If the user doesn't own the product.
            ValidationError: If nothing is sent, or a required field is set to null.
        """
        product = await self.get(product_id, db)
        self.verify_owner_or_superuser(current_user, product)

        update_data = values.model_dump(exclude_unset=True)
        if not update_data:
            raise ValidationError("No fields to update")
        null_fields = [field for field in _REQUIRED_FIELDS if update_data.get(field, "") is None]
        if null_fields:
            raise ValidationError(
                "name and price cannot be null",
                errors={field: [f"The {field} field cannot be null."] for field in null_fields},
            )

        await crud_products.update(db=db, object=update_data, id=product_id)
        return await self.get(product_id, db)

    async def delete(self, product_id: int, current_user: dict[str, Any], db: AsyncSession) -> None:
        """Soft delete a product the current user owns (or any product, for a superuser).

        Raises:
            ResourceNotFoundError: If the product doesn't exist.
            PermissionDeniedError: If the user doesn't own the product.
        """
        product = await self.get(product_id, db)
        self.verify_owner_or_superuser(current_user, product)

        await crud_products.delete(db=db, id=product_id)

    @staticmethod
    def verify_owner_or_superuser(current_user: dict[str, Any], product: dict[str, Any]) -> None:
        """Allow the product's owner or a superuser; reject everyone else."""
        if current_user.get("is_superuser", False):
            return
        if current_user["id"] != product["owner_id"]:
            raise PermissionDeniedError("Only the owner can modify this product")

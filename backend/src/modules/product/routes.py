from typing import Any

from fastapi import APIRouter
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from .dependencies import ProductServiceDep
from .schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(tags=["Products"])


@router.post(
    "/",
    status_code=201,
    response_model=ProductRead,
    summary="Create Product",
    description="Creates a product owned by the current user. The owner is taken from the session, never the request body.",
    responses={
        201: {"description": "Product created"},
        401: {"description": "Not authenticated"},
        422: {"description": "Invalid product data"},
    },
    response_description="The created product",
)
async def create_product(
    product: ProductCreate,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
) -> dict[str, Any]:
    """Create a product for the current user."""
    return await product_service.create(product, owner_id=current_user["id"], db=db)


@router.get(
    "/",
    response_model=PaginatedListResponse[ProductRead],
    summary="List Products",
    description="Paginated list of all active products, newest first.",
    responses={401: {"description": "Not authenticated"}},
    response_description="A paginated list of products",
)
async def get_products(
    _: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    """List active products."""
    products = await product_service.get_paginated(skip=compute_offset(page, items_per_page), limit=items_per_page, db=db)
    return paginated_response(crud_data=products, page=page, items_per_page=items_per_page)


@router.get(
    "/me",
    response_model=PaginatedListResponse[ProductRead],
    summary="List My Products",
    description="Paginated list of the active products owned by the current user, newest first.",
    responses={401: {"description": "Not authenticated"}},
    response_description="A paginated list of the current user's products",
)
async def get_my_products(
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    """List the current user's products."""
    products = await product_service.get_paginated(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
        owner_id=current_user["id"],
    )
    return paginated_response(crud_data=products, page=page, items_per_page=items_per_page)


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    summary="Get Product",
    responses={401: {"description": "Not authenticated"}, 404: {"description": "Product not found"}},
    response_description="The requested product",
)
async def get_product(
    product_id: int,
    _: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
) -> dict[str, Any]:
    """Get a product by id."""
    return await product_service.get(product_id, db)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Update Product",
    description="Updates a product. Only the owner (or a superuser) can do this. Only the fields sent are changed.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the owner of this product"},
        404: {"description": "Product not found"},
        422: {"description": "Invalid product data"},
    },
    response_description="The updated product",
)
async def update_product(
    product_id: int,
    values: ProductUpdate,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
) -> dict[str, Any]:
    """Update a product."""
    return await product_service.update(product_id, values, current_user, db)


@router.delete(
    "/{product_id}",
    summary="Delete Product",
    description="Soft-deletes a product. Only the owner (or a superuser) can do this.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the owner of this product"},
        404: {"description": "Product not found"},
    },
    response_description="Success confirmation message",
)
async def delete_product(
    product_id: int,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    product_service: ProductServiceDep,
) -> dict[str, str]:
    """Soft delete a product."""
    await product_service.delete(product_id, current_user, db)
    return {"message": "Product deleted"}

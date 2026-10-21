from typing import Annotated

from fastapi import Depends

from .service import ProductService


def get_product_service() -> ProductService:
    """Get product service instance."""
    return ProductService()


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

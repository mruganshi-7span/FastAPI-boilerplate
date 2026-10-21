from fastcrud import FastCRUD

from .models import Product

crud_products: FastCRUD = FastCRUD(Product)

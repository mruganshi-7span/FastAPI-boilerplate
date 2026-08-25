from fastapi import Request
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.db.base import QB
from app.db.pagination import paginate
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryPage, CategoryRead, CategoryUpdate, CategoryUser


def get_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise NotFoundException("category.not_found")
    return category


def list_categories(db: Session, qb: QB, request: Request) -> CategoryPage:
    # Filters/sort/includes from qb are applied inside paginate() itself, not here — cursor mode
    # needs to control sort to keep it consistent with its keyset comparison.
    base_stmt = select(Category)
    return paginate(db, base_stmt, request, qb, to_category_read)


def create_category(db: Session, payload: CategoryCreate) -> Category:
    if db.get(User, payload.user_id) is None:
        raise ValidationException(errors={"user_id": ["user.not_found"]})

    category = Category(name=payload.name, user_id=payload.user_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category_id: int, payload: CategoryUpdate) -> Category:
    category = get_category(db, category_id)

    if payload.user_id is not None and db.get(User, payload.user_id) is None:
        raise ValidationException(errors={"user_id": ["user.not_found"]})

    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int) -> None:
    category = get_category(db, category_id)
    category.soft_delete()
    db.commit()


def to_category_read(category: Category) -> CategoryRead:
    user = None
    if "user" not in inspect(category).unloaded:
        user = CategoryUser(id=category.user.id, name=category.user.name, email=category.user.email)

    return CategoryRead(
        id=category.id,
        name=category.name,
        user_id=category.user_id,
        user=user,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )

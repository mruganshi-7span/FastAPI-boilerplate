from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import QB, get_current_user, get_db, get_qb
from app.core.config import get_settings
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryPage, CategoryRead, CategoryUpdate
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["Categories"], dependencies=[Depends(get_current_user)])

settings = get_settings()
category_qb = get_qb(Category)


@router.get("", response_model=CategoryPage)
def list_categories(
    request: Request,
    # Declared here only so /docs documents and validates them (out-of-range values 422 before
    # this ever runs) — paginate() re-reads the actual values straight off `request` itself, so
    # they're intentionally unused as Python variables in this body.
    page: int = Query(default=1, ge=1, description="Ignored once `cursor` is present"),
    per_page: int = Query(
        default=settings.pagination_limit, ge=-1, le=100, description="-1 returns every record, unpaginated"
    ),
    cursor: str | None = Query(
        default=None,
        description="Opt into cursor pagination instead of page-based — use the `next_cursor`/"
        "`prev_cursor` from a previous response, not something to construct by hand. Doesn't "
        "degrade on deep pages the way `page=` does on very large tables.",
    ),
    direction: str | None = Query(default=None, description="'next' or 'prev', used together with `cursor`"),
    qb: QB = Depends(category_qb),
    db: Session = Depends(get_db),
) -> CategoryPage:
    return category_service.list_categories(db, qb, request)


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> CategoryRead:
    return category_service.to_category_read(category_service.create_category(db, payload))


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, db: Session = Depends(get_db)) -> CategoryRead:
    return category_service.to_category_read(category_service.get_category(db, category_id))


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)) -> CategoryRead:
    return category_service.to_category_read(category_service.update_category(db, category_id, payload))


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db)) -> None:
    category_service.delete_category(db, category_id)

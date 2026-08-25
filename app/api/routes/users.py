from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import QB, get_current_user, get_db, get_qb
from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(get_current_user)])

settings = get_settings()
user_qb = get_qb(User)


@router.get("", response_model=UserPage)
def list_users(
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
    qb: QB = Depends(user_qb),
    db: Session = Depends(get_db),
) -> UserPage:
    return user_service.list_users(db, qb, request)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    return user_service.to_user_read(user_service.create_user(db, payload))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserRead:
    return user_service.to_user_read(user_service.get_user(db, user_id))


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> UserRead:
    return user_service.to_user_read(user_service.update_user(db, user_id, payload))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    user_service.delete_user(db, user_id)

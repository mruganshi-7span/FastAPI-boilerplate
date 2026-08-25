from fastapi import Request
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import hash_password
from app.db.base import QB
from app.db.pagination import paginate
from app.models.mediable import MEDIABLE_TYPE_USER
from app.models.user import User
from app.schemas.media import MediaConfirmRequest
from app.schemas.mediable import MediableCreate
from app.schemas.user import UpdateMeRequest, UserCategoryRead, UserCreate, UserPage, UserRead, UserUpdate
from app.services import auth_service, media_service, mediable_service

PROFILE_TAG = "profile"


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundException("user.not_found")
    return user


def get_user_by_email(db: Session, email: str) -> User | None:
    # include_deleted=True is deliberate — see the matching note in auth_service.register_user.
    stmt = select(User).where(User.email == email).execution_options(include_deleted=True)
    return db.scalar(stmt)


def list_users(db: Session, qb: QB, request: Request) -> UserPage:
    # profile is always read during serialization below — always eager-load it, independent of
    # ?include=, or a page of N users triggers N lazy-loaded profile queries. Filters/sort/includes
    # from qb are applied inside paginate() itself, not here — cursor mode needs to control sort.
    base_stmt = select(User).options(selectinload(User.profile))
    return paginate(db, base_stmt, request, qb, to_user_read)


def create_user(db: Session, payload: UserCreate) -> User:
    if get_user_by_email(db, payload.email) is not None:
        raise ValidationException(errors={"email": ["email.already_taken"]})

    user = User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if payload.profile is not None:
        _set_profile(db, user, payload.profile)

    return user


def update_user(db: Session, user_id: int, payload: UserUpdate | UpdateMeRequest) -> User:
    user = get_user(db, user_id)

    if payload.email is not None and payload.email != user.email:
        if get_user_by_email(db, payload.email) is not None:
            raise ValidationException(errors={"email": ["email.already_taken"]})

    fields = payload.model_dump(exclude_unset=True, exclude={"password", "profile"})
    for field, value in fields.items():
        setattr(user, field, value)

    if payload.password is not None:
        user.password = hash_password(payload.password)

    db.commit()
    db.refresh(user)

    if "profile" in payload.model_fields_set:
        _set_profile(db, user, payload.profile)

    return user


def delete_user(db: Session, user_id: int) -> None:
    user = get_user(db, user_id)
    user.soft_delete()
    db.commit()

    auth_service.revoke_all_refresh_tokens(db, user.id)


def to_user_read(user: User) -> UserRead:
    # Checking `.unloaded` (not just accessing the attribute) matters: accessing an unloaded
    # relationship on an already-fetched object triggers a lazy-load query right there — this is
    # what lets a single-resource GET stay lazy-load-free while a list endpoint stays eager-load-
    # or-nothing, using the exact same to_user_read for both.
    categories = None
    if "categories" not in inspect(user).unloaded:
        categories = [UserCategoryRead(id=category.id, name=category.name) for category in user.categories]

    return UserRead(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        profile=media_service.to_media_read(user.profile) if user.profile else None,
        categories=categories,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _set_profile(db: Session, user: User, profile: MediaConfirmRequest | None) -> None:
    """Confirm-and-attach in one step: `user` is who the profile picture is being attached to —
    not necessarily whoever called this endpoint, e.g. an admin creating another user's account
    with a picture they uploaded themselves.
    """
    if profile is not None:
        media = media_service.confirm_upload(db, profile)
        mediable_service.create_mediable(
            db,
            MediableCreate(media_id=media.id, mediable_type=MEDIABLE_TYPE_USER, mediable_id=user.id, tag=PROFILE_TAG),
        )
        return

    existing = mediable_service.find_mediable(
        db, mediable_type=MEDIABLE_TYPE_USER, mediable_id=user.id, tag=PROFILE_TAG
    )
    if existing is not None:
        mediable_service.delete_mediable(db, existing.id)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.models.media import Media
from app.models.mediable import Mediable
from app.models.user import User
from app.schemas.mediable import MediableCreate
from app.services import storage_service

# Registry of mediable_type -> model class, so an attach request can be checked against a real
# record instead of trusting an arbitrary (type, id) pair. Extend this as more entities become mediable.
_MEDIABLE_TYPES: dict[str, type] = {
    "user": User,
}


def create_mediable(db: Session, payload: MediableCreate) -> Mediable:
    model_class = _MEDIABLE_TYPES.get(payload.mediable_type)
    if model_class is None:
        raise ValidationException(errors={"mediable_type": ["mediable.unsupported_type"]})

    if db.get(model_class, payload.mediable_id) is None:
        raise ValidationException(
            errors={"mediable_id": [("mediable.target_not_found", {"type": payload.mediable_type})]}
        )

    media = db.get(Media, payload.media_id)
    if media is None:
        raise ValidationException(errors={"media_id": ["mediable.media_not_found"]})

    # Sync semantics: a (mediable_type, mediable_id, tag) triple holds at most one media at a time —
    # attaching a new one replaces whatever was there before, same as Laravel's syncMedia().
    previous = find_mediable(db, mediable_type=payload.mediable_type, mediable_id=payload.mediable_id, tag=payload.tag)
    if previous is not None and previous.media_id == media.id:
        return previous

    mediable = Mediable(
        media_id=media.id,
        mediable_type=payload.mediable_type,
        mediable_id=payload.mediable_id,
        tag=payload.tag,
    )
    db.add(mediable)
    db.commit()
    db.refresh(mediable)

    if previous is not None:
        _delete_mediable_and_media(db, previous)

    return mediable


def find_mediable(db: Session, *, mediable_type: str, mediable_id: int, tag: str) -> Mediable | None:
    return db.scalar(
        select(Mediable).where(
            Mediable.mediable_type == mediable_type,
            Mediable.mediable_id == mediable_id,
            Mediable.tag == tag,
        )
    )


def delete_mediable(db: Session, mediable_id: int) -> None:
    mediable = db.get(Mediable, mediable_id)
    if mediable is None:
        raise NotFoundException("mediable.not_found")

    _delete_mediable_and_media(db, mediable)


def _delete_mediable_and_media(db: Session, mediable: Mediable) -> None:
    media = db.get(Media, mediable.media_id)
    db.delete(mediable)
    db.commit()

    if media is not None:
        db.delete(media)
        db.commit()
        storage_service.delete_object(key=media.key)

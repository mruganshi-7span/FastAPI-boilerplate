from typing import Annotated

from fastapi import Depends

from .service import MediaService


def get_media_service() -> MediaService:
    """Get media service instance."""
    return MediaService()


MediaServiceDep = Annotated[MediaService, Depends(get_media_service)]

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.media import MediaUploadRequest, MediaUploadUrlResponse
from app.services import media_service

router = APIRouter(prefix="/media", tags=["Media"], dependencies=[Depends(get_current_user)])


@router.post("/upload-url", response_model=MediaUploadUrlResponse)
def create_upload_url(payload: MediaUploadRequest) -> MediaUploadUrlResponse:
    return media_service.create_upload_url(payload)

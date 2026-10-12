from typing import Any

from fastapi import APIRouter

from ...infrastructure.dependencies import CurrentUserDep
from .dependencies import MediaServiceDep
from .schemas import MediaUploadRequest, MediaUploadUrlResponse

router = APIRouter(tags=["Media"])


@router.post(
    "/upload-url",
    response_model=MediaUploadUrlResponse,
    summary="Create Presigned Upload URL",
    description="""
            Returns a short-lived presigned URL for uploading one file straight to S3.

            The file never passes through the API:
            1. Call this endpoint with the file's content type and a tag (e.g. `profile`)
            2. `PUT` the raw file bytes to `upload_url`, sending the returned `headers`
               (the `Content-Type` is part of the signature)
            3. Confirm the upload with the returned `key` on the feature endpoint,
               e.g. `PUT /api/v1/users/me/profile-image`

            Keys are scoped to the requesting user, so only they can confirm the upload.
            Size and type are checked against what S3 actually stored when the upload is confirmed.
            """,
    responses={
        401: {"description": "Not authenticated"},
        422: {"description": "Content type not allowed for this tag"},
        503: {"description": "File storage is unavailable"},
    },
    response_description="The presigned upload URL and the key it is bound to",
)
async def create_upload_url(
    payload: MediaUploadRequest,
    current_user: CurrentUserDep,
    media_service: MediaServiceDep,
) -> dict[str, Any]:
    """Create a presigned S3 upload URL for the current user."""
    return await media_service.create_upload_url(payload, owner_id=current_user["id"])

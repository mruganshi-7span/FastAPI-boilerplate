from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.dependencies import load_permissions, require_permissions
from ...infrastructure.dependencies import (
    AsyncSessionDep,
    CurrentPermissionsDep,
    CurrentSuperUserDep,
    CurrentUserDep,
)
from ..common.includes import attach_includes, include_param
from ..media.schemas import MediaConfirmRequest
from .dependencies import UserServiceDep
from .models import User
from .schemas import (
    UserCreate,
    UserProfileRead,
    UserRead,
    UserUpdate,
)

router = APIRouter(tags=["Users"])

# Reads ?include=... for the user list; the allowed names come from User.__includable__.
user_includes = include_param(User)


@router.post(
    "/",
    status_code=201,
    response_model=UserRead,
    summary="Create New User Account",
    description="""
           Creates a new user account in the system.

           This endpoint allows registration of new users with their basic information:
           - Full name
           - Username (must be lowercase alphanumeric)
           - Email address
           - Password (with security requirements)
           """,
    responses={
        201: {"description": "User account created successfully"},
        400: {"description": "Invalid user data"},
        409: {"description": "Username or email already exists"},
    },
    response_description="The created user profile with assigned ID",
)
async def create_user(
    user: UserCreate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Create a new user account."""
    return await user_service.create(user, db)


@router.get(
    "/",
    response_model=PaginatedListResponse[UserRead],
    # Leave out fields nobody set, so `products` only appears when ?include=products was sent.
    response_model_exclude_unset=True,
    summary="List All Users",
    description="""
           Retrieves a paginated list of all users in the system.

           Requires the `user.read` permission, which a role grants; superusers
           always pass. The results include basic profile information for each
           user. Send `?include=products` to also get each user's products.

           For security reasons, sensitive information like passwords is never included
           in the response.
           """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires the user.read permission"},
    },
    response_description="A paginated list of users with total count and pagination metadata",
    dependencies=[require_permissions("user.read")],
)
async def get_users(
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    includes: Annotated[list[str], Depends(user_includes)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    """Get paginated list of users."""
    users_data = await user_service.get_paginated(skip=compute_offset(page, items_per_page), limit=items_per_page, db=db)
    users_data["data"] = await user_service.with_profile_images(list(users_data["data"]), db)
    users_data["data"] = await attach_includes(db, User, users_data["data"], includes)

    return paginated_response(crud_data=users_data, page=page, items_per_page=items_per_page)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get Current User Profile",
    description="""
            Retrieves the profile information of the currently authenticated user.

            This endpoint provides users with their own profile data including:
            - Basic profile information (name, username, email)
            - Profile image URL
            - Authentication details (superuser status, email verification)

            This is a convenient way for frontend applications to get the current
            user's information for display or personalization purposes.
            """,
    responses={401: {"description": "Not authenticated"}},
    response_description="The current user's profile data",
)
async def get_current_user_profile(
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Get current authenticated user's profile."""
    return await user_service.with_profile_image(current_user, db)


@router.put(
    "/me/profile-image",
    response_model=UserRead,
    summary="Set Current User Profile Image",
    description="""
            Sets the current user's profile image from a file already uploaded to S3.

            Flow:
            1. `POST /api/v1/media/upload-url` with `{"content_type": "image/png", "tag": "profile"}`
            2. `PUT` the image bytes to the returned `upload_url` with the returned `headers`
            3. Call this endpoint with the returned `key`

            The file's size and type are read from S3 and validated (images only, up to
            `MEDIA_MAX_UPLOAD_SIZE_BYTES`). Any previous profile image is replaced and its
            file deleted. The response carries `profile_image.url`, a presigned download URL.
            """,
    responses={
        200: {"description": "Profile image set"},
        401: {"description": "Not authenticated"},
        409: {"description": "This upload was already confirmed"},
        422: {"description": "Unknown key, nothing uploaded, or file type/size not allowed"},
        503: {"description": "File storage is unavailable"},
    },
    response_description="The current user's profile with the new profile image",
)
async def set_current_user_profile_image(
    payload: MediaConfirmRequest,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Confirm an uploaded file as the current user's profile image."""
    await user_service.set_profile_image(current_user["id"], payload, db)
    return await user_service.with_profile_image(current_user, db)


@router.delete(
    "/me/profile-image",
    summary="Remove Current User Profile Image",
    description="""
            Removes the current user's uploaded profile image and deletes its file from S3.

            Succeeds even if no image is set.
            """,
    responses={200: {"description": "Profile image removed"}, 401: {"description": "Not authenticated"}},
    response_description="Success confirmation message",
)
async def remove_current_user_profile_image(
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Remove the current user's profile image."""
    removed = await user_service.remove_profile_image(current_user["id"], db)
    return {"message": "Profile image removed" if removed else "No profile image to remove"}


@router.get(
    "/{username}",
    response_model=UserProfileRead,
    # Leave out fields nobody set, so `products` only appears when ?include=products was sent.
    response_model_exclude_unset=True,
    summary="Get User Profile by Username",
    description="""
            Retrieves a user's public profile by their unique username.

            Any signed-in user can look up any other active user. The response carries
            the display fields only - no email address - so the lookup can't be used to
            collect addresses. Read your own full record from `/users/me`.
            Send `?include=products` to also get the user's products.

            Note that usernames are case-sensitive in lookup operations.
            """,
    responses={401: {"description": "Not authenticated"}, 404: {"description": "User not found"}},
    response_description="The requested user's profile data",
)
async def get_user_by_username(
    username: str,
    _: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    includes: Annotated[list[str], Depends(user_includes)],
) -> dict[str, Any]:
    """Get user profile by username."""
    user = await user_service.get_by_username(username, db)
    user = await user_service.with_profile_image(user, db)
    [user] = await attach_includes(db, User, [user], includes)
    return user


@router.get(
    "/active-and-inactive/{username}",
    response_model=UserRead,
    summary="Get Active and Inactive User Profile by Username(Admin)",
    description="""
            Retrieve a user's profile information by their unique username.

            This endpoint can be used to look up any user in the system by their
            username. It returns the same profile data structure as other user
            endpoints but does not include sensitive information.

            Note that usernames are case-sensitive in lookup operations.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "User not found"},
    },
    response_description="the requested user's profile data",
)
async def get_active_and_inactive_user_by_username(
    username: str,
    db: AsyncSessionDep,
    _: CurrentSuperUserDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Get active and inactive profile by username."""
    user = await user_service.get_active_and_inactive_by_username(username, db)
    return await user_service.with_profile_image(user, db)


@router.patch(
    "/{username}",
    summary="Update User Profile",
    description="""
            Updates a user's profile information.

            This endpoint allows users to modify their own profile data, and users
            holding the `user.update` permission to modify another user's data. Only
            the fields provided in the request will be updated, and all fields are
            optional.

            Permission rules:
            - Regular users can only update their own profiles
            - Superusers can update any user's profile
            - A `user.update` holder can update another user only when that user is
              not a superuser and holds no permission the requester lacks, and cannot
              change another user's email address

            Username and email changes are validated to ensure uniqueness.
            """,
    responses={
        200: {"description": "Profile updated successfully"},
        400: {"description": "Invalid profile data"},
        403: {"description": "Not authorized to update this profile"},
        404: {"description": "User not found"},
        409: {"description": "Username or email already exists"},
    },
    response_description="Success confirmation message",
)
async def update_user_profile(
    username: str,
    values: UserUpdate,
    current_user: CurrentUserDep,
    permissions: CurrentPermissionsDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Update user profile information."""
    await user_service.verify_update_permission(current_user, username, permissions)
    user = await user_service.get_by_username(username, db)

    if not user_service.is_self_or_superuser(current_user, user["username"]):
        target_permissions = await load_permissions(db, user["id"])
        user_service.verify_no_privilege_escalation(user, values, permissions, target_permissions)

    await user_service.update(user["id"], values, db)
    return {"message": "User updated successfully"}


@router.delete(
    "/{username}",
    summary="Deactivate User Account",
    description="""
            Soft-deletes (deactivates) a user account.

            This endpoint performs a logical deletion of a user account, marking it
            as deactivated in the system rather than permanently removing it. This allows
            for potential reactivation in the future.

            Permission rules:
            - Regular users can only deactivate their own accounts
            - Administrators can deactivate any user's account

            Deactivated accounts cannot be used for login and are typically hidden
            from regular user listings.
            """,
    responses={
        200: {"description": "Account deactivated successfully"},
        403: {"description": "Not authorized to deactivate this account"},
        404: {"description": "User not found"},
    },
    response_description="Success confirmation message",
)
async def delete_user_account(
    username: str,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Soft delete a user account."""
    await user_service.verify_user_permission(current_user, username, "delete this account")
    user = await user_service.get_by_username(username, db)

    await user_service.delete(user["id"], db)
    return {"message": "User account deactivated"}


@router.delete(
    "/db/{username}",
    summary="GDPR Delete User (Admin)",
    description="""
            GDPR/LGPD compliant user deletion with data anonymization.

            This admin-only endpoint anonymizes user PII while preserving business data
            integrity and maintaining referential relationships for conversations and
            analytics data.

            This operation:
            - Removes personally identifiable information (PII)
            - Retains email for legal compliance purposes
            - Prevents future login by clearing credentials
            - Maintains foreign key relationships (conversations, logs)
            - Logs the deletion event with legal basis for audit compliance

            Unlike hard deletion, this approach:
            - Complies with GDPR Article 17 (Right to Erasure)
            - Preserves business analytics data
            - Eliminates foreign key constraint violations
            - Maintains audit trails for legal requirements

            This operation is needed for:
            - GDPR/LGPD data deletion requests
            - Legal compliance while preserving business data
            - Safe user removal without breaking referential integrity
            """,
    responses={
        200: {"description": "User anonymized successfully"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "User not found"},
    },
    response_description="Success confirmation message",
)
async def gdpr_delete_user(
    username: str,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, str]:
    """GDPR compliant user anonymization (admin only)."""
    user = await user_service.get_active_and_inactive_by_username(username, db)
    await user_service.anonymize_user(user["id"], db)
    return {"message": "User data anonymized in compliance with GDPR"}

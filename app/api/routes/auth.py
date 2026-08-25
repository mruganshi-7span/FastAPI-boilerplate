from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.localization import request_locale, translate
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    TokenRefresh,
    UserLogin,
    UserRegister,
)
from app.schemas.user import UpdateMeRequest, UserRead
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> UserRead:
    return user_service.to_user_read(auth_service.register_user(db, payload))


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    return auth_service.authenticate_user(db, payload)


@router.post("/refresh", response_model=Token)
def refresh(payload: TokenRefresh, db: Session = Depends(get_db)) -> Token:
    return auth_service.refresh_tokens(db, payload.refresh_token)


@router.post("/logout")
def logout(payload: TokenRefresh, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    auth_service.revoke_refresh_token(db, payload.refresh_token)
    return {"message": translate("auth.logged_out", locale=request_locale(request))}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return user_service.to_user_read(current_user)


@router.put("/me", response_model=UserRead)
def update_me(
    payload: UpdateMeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    return user_service.to_user_read(user_service.update_user(db, current_user.id, payload))


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    locale = request_locale(request)
    await auth_service.request_password_reset(db, payload, locale)
    return {"message": translate("auth.forgot_password_sent", locale=locale)}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    auth_service.reset_password(db, payload)
    return {"message": translate("auth.password_reset_done", locale=request_locale(request))}

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException, ValidationException
from app.core.queue import get_or_create_redis_pool
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_opaque_token,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import ForgotPasswordRequest, ResetPasswordRequest, Token, UserLogin, UserRegister

settings = get_settings()


def register_user(db: Session, payload: UserRegister) -> User:
    # include_deleted=True is deliberate: the `email` column has a single, unscoped unique
    # constraint, so a soft-deleted user's email is still physically taken either way.
    stmt = select(User).where(User.email == payload.email).execution_options(include_deleted=True)
    existing = db.scalar(stmt)
    if existing is not None:
        raise ValidationException(errors={"email": ["email.already_taken"]})

    user = User(name=payload.name, email=payload.email, password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, payload: UserLogin) -> Token:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password):
        raise UnauthorizedException("auth.invalid_credentials")

    if not user.is_active:
        raise UnauthorizedException("auth.account_deactivated")

    return _issue_tokens(db, user)


def refresh_tokens(db: Session, raw_refresh_token: str) -> Token:
    refresh_token = _resolve_refresh_token(db, raw_refresh_token)
    refresh_token.revoked_at = datetime.now(UTC)
    db.commit()

    user = db.get(User, refresh_token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("auth.account_unavailable")

    return _issue_tokens(db, user)


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> None:
    refresh_token = _resolve_refresh_token(db, raw_refresh_token)
    refresh_token.revoked_at = datetime.now(UTC)
    db.commit()


def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    """Sign a user out everywhere — used on password reset and on account deletion."""
    active_refresh_tokens = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    )
    now = datetime.now(UTC)
    for token in active_refresh_tokens:
        token.revoked_at = now

    db.commit()


async def request_password_reset(db: Session, payload: ForgotPasswordRequest, locale: str) -> None:
    # Validates the email up front and reports it explicitly — same shape as Laravel's stock
    # Password::sendResetLink, which raises a ValidationException on `passwords.user` when the
    # email doesn't match an account. This is a deliberate UX-over-anti-enumeration tradeoff: it
    # does let a caller probe which emails are registered. Accepted here on purpose, not an oversight.
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise ValidationException(errors={"email": ["email.not_found"]})

    if not user.is_active:
        raise UnauthorizedException("auth.account_deactivated")

    secret = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.password_reset_token_expire_minutes)
    reset_token = PasswordResetToken(user_id=user.id, token_hash=hash_opaque_token(secret), expires_at=expires_at)
    db.add(reset_token)
    db.commit()
    db.refresh(reset_token)

    raw_token = f"{reset_token.id}:{secret}"
    reset_link = f"{settings.frontend_url}/reset-password?token={quote(raw_token)}"

    # Connecting to Redis is deferred to this point — after every validation above has already
    # passed — so a Redis outage surfaces as "email not found" being checked correctly instead of
    # a connection error masking whether the validation ran at all.
    redis = await get_or_create_redis_pool()

    # `locale` is captured from the request that triggered this, not read at send time — the arq
    # worker sending the email has no HTTP request of its own to read a `locale` header from.
    await redis.enqueue_job(
        "send_password_reset_email", name=user.name, email=user.email, reset_link=reset_link, locale=locale
    )


def reset_password(db: Session, payload: ResetPasswordRequest) -> None:
    # Same shape as Laravel's Password::reset(), which takes {email, token, password}: validate the
    # email exists first, and report it explicitly (same tradeoff as request_password_reset above).
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise ValidationException(errors={"email": ["email.not_found"]})

    reset_token = _resolve_password_reset_token(db, payload.token)

    # The token is what actually proves ownership — cryptographically tying it to whatever user_id
    # it was issued for. `email` here is a corroborating check, not an alternate lookup: without
    # this, a token issued for one account could be replayed against a different email address in
    # the request and still be accepted, since the code below never used `payload.email` to find
    # the user before this check existed.
    if reset_token.user_id != user.id:
        raise UnauthorizedException("auth.reset_link_invalid")

    user.password = hash_password(payload.password)
    reset_token.used_at = datetime.now(UTC)
    db.commit()

    # A password reset is a signal the account may have been compromised — sign out everywhere.
    revoke_all_refresh_tokens(db, user.id)


def _resolve_refresh_token(db: Session, raw_refresh_token: str) -> RefreshToken:
    invalid_token_key = "auth.refresh_token_invalid"

    try:
        token_id_str, secret = raw_refresh_token.split(":", 1)
        token_id = int(token_id_str)
    except ValueError as exc:
        raise UnauthorizedException(invalid_token_key) from exc

    refresh_token = db.get(RefreshToken, token_id)
    if refresh_token is None or not verify_opaque_token(secret, refresh_token.token_hash):
        raise UnauthorizedException(invalid_token_key)

    if refresh_token.revoked_at is not None:
        raise UnauthorizedException(invalid_token_key)

    if _is_expired(refresh_token.expires_at):
        raise UnauthorizedException(invalid_token_key)

    return refresh_token


def _resolve_password_reset_token(db: Session, raw_token: str) -> PasswordResetToken:
    invalid_token_key = "auth.reset_link_invalid"

    try:
        token_id_str, secret = raw_token.split(":", 1)
        token_id = int(token_id_str)
    except ValueError as exc:
        raise UnauthorizedException(invalid_token_key) from exc

    reset_token = db.get(PasswordResetToken, token_id)
    if reset_token is None or not verify_opaque_token(secret, reset_token.token_hash):
        raise UnauthorizedException(invalid_token_key)

    if reset_token.used_at is not None:
        raise UnauthorizedException(invalid_token_key)

    if _is_expired(reset_token.expires_at):
        raise UnauthorizedException(invalid_token_key)

    return reset_token


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


def _issue_tokens(db: Session, user: User) -> Token:
    access_token = create_access_token(subject=str(user.id))

    secret = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    refresh_token_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_opaque_token(secret),
        expires_at=expires_at,
    )
    db.add(refresh_token_row)
    db.commit()
    db.refresh(refresh_token_row)

    raw_refresh_token = f"{refresh_token_row.id}:{secret}"

    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )

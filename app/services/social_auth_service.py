from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.security import generate_opaque_token, hash_opaque_token, verify_opaque_token
from app.models.social_account import SocialAccount
from app.models.social_login_code import SocialLoginCode
from app.models.user import User
from app.schemas.auth import Token
from app.services import auth_service

settings = get_settings()


def resolve_user(db: Session, provider: str, userinfo: Mapping[str, Any]) -> User:
    """Map a provider identity (already verified by Authlib) to a local user: existing link first,
    then auto-link by verified email, otherwise create a password-less user.
    """
    provider_user_id = str(userinfo["sub"])

    social_account = db.scalar(
        select(SocialAccount).where(
            SocialAccount.provider == provider, SocialAccount.provider_user_id == provider_user_id
        )
    )
    if social_account is not None:
        # db.get goes through the soft-delete filter, so a soft-deleted user comes back as None.
        user = db.get(User, social_account.user_id)
        if user is None:
            raise UnauthorizedException("auth.account_unavailable")
        _ensure_active(user)
        return user

    # Auto-linking trusts the provider's claim that this person owns the email. Without that claim,
    # anyone could sign up at the provider with someone else's address and take over their account.
    email = userinfo.get("email")
    if not email or userinfo.get("email_verified") not in (True, "true"):
        raise UnauthorizedException("auth.social_email_unverified")

    # include_deleted=True: the email unique constraint also covers soft-deleted rows, so creating
    # a new user with this email would fail at the DB. Report it as unavailable instead.
    user = db.scalar(select(User).where(User.email == email).execution_options(include_deleted=True))
    if user is not None and user.is_deleted:
        raise UnauthorizedException("auth.account_unavailable")

    if user is None:
        user = User(name=userinfo.get("name") or email, email=email, password=None)
        db.add(user)
        db.flush()
    else:
        _ensure_active(user)

    db.add(SocialAccount(user_id=user.id, provider=provider, provider_user_id=provider_user_id, email=email))
    db.commit()
    db.refresh(user)
    return user


def issue_login_code(db: Session, user: User) -> str:
    secret = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.social_login_code_expire_seconds)
    login_code = SocialLoginCode(user_id=user.id, code_hash=hash_opaque_token(secret), expires_at=expires_at)
    db.add(login_code)
    db.commit()
    db.refresh(login_code)
    return f"{login_code.id}:{secret}"


def exchange_login_code(db: Session, raw_code: str) -> Token:
    invalid_code_key = "auth.social_login_failed"

    try:
        code_id_str, secret = raw_code.split(":", 1)
        code_id = int(code_id_str)
    except ValueError as exc:
        raise UnauthorizedException(invalid_code_key) from exc

    login_code = db.get(SocialLoginCode, code_id)
    if login_code is None or not verify_opaque_token(secret, login_code.code_hash):
        raise UnauthorizedException(invalid_code_key)

    if login_code.used_at is not None or auth_service._is_expired(login_code.expires_at):
        raise UnauthorizedException(invalid_code_key)

    login_code.used_at = datetime.now(UTC)
    db.commit()

    # Re-checked here: the account may have been deactivated or deleted since the callback ran.
    user = db.get(User, login_code.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("auth.account_unavailable")

    return auth_service._issue_tokens(db, user)


def _ensure_active(user: User) -> None:
    if not user.is_active:
        raise UnauthorizedException("auth.account_deactivated")

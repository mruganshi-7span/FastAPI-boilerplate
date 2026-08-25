import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

TOKEN_TYPE_ACCESS = "access"
_MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_BCRYPT_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:_MAX_BCRYPT_PASSWORD_BYTES]
    return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "type": TOKEN_TYPE_ACCESS, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        return None

    return payload


def generate_opaque_token() -> str:
    """A high-entropy random token for refresh tokens and password-reset links."""
    return secrets.token_urlsafe(64)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_opaque_token(plain_token: str, hashed_token: str) -> bool:
    return hmac.compare_digest(hash_opaque_token(plain_token), hashed_token)

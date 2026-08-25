import logging
from datetime import UTC, datetime

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken

logger = logging.getLogger(__name__)


def cleanup_expired_tokens(db: Session) -> tuple[int, int]:
    """Delete refresh tokens and password-reset tokens that are expired or already consumed.

    A revoked/used token is already permanently rejected by auth_service's own checks — there's no
    reason to wait for its natural expiry before removing it too.
    """
    now = datetime.now(UTC)

    refresh_result = db.execute(
        delete(RefreshToken).where(or_(RefreshToken.expires_at < now, RefreshToken.revoked_at.is_not(None)))
    )
    reset_result = db.execute(
        delete(PasswordResetToken).where(
            or_(PasswordResetToken.expires_at < now, PasswordResetToken.used_at.is_not(None))
        )
    )
    db.commit()

    deleted_refresh_tokens = refresh_result.rowcount
    deleted_reset_tokens = reset_result.rowcount

    logger.info(
        "Token cleanup: removed %d refresh token(s) and %d password reset token(s).",
        deleted_refresh_tokens,
        deleted_reset_tokens,
    )

    return deleted_refresh_tokens, deleted_reset_tokens

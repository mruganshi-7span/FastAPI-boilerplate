import logging
from urllib.parse import quote

import httpx2
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.oauth import oauth
from app.schemas.auth import SocialCodeExchange, Token
from app.services import social_auth_service

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Social Auth"])

_GOOGLE = "google"


@router.get("/google/login")
async def google_login(request: Request):
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    # This is a browser navigation coming back from Google, not an API call — every outcome,
    # including errors, is a redirect to the frontend rather than a JSON response.
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            raise OAuthError(error="missing_userinfo", description="Google response had no id_token userinfo")

        user = social_auth_service.resolve_user(db, _GOOGLE, userinfo)
        code = social_auth_service.issue_login_code(db, user)
    # httpx2.HTTPError covers Google being unreachable during the token exchange or metadata fetch.
    except (OAuthError, httpx2.HTTPError) as exc:
        logger.warning("Google login failed: %s", exc)
        return _frontend_redirect(error="auth.social_login_failed")
    except AppException as exc:
        return _frontend_redirect(error=exc.key)

    return _frontend_redirect(code=code)


@router.post("/social/exchange", response_model=Token)
def social_exchange(payload: SocialCodeExchange, db: Session = Depends(get_db)) -> Token:
    return social_auth_service.exchange_login_code(db, payload.code)


def _frontend_redirect(*, code: str | None = None, error: str | None = None) -> RedirectResponse:
    query = f"code={quote(code)}" if code is not None else f"error={quote(error or 'auth.social_login_failed')}"
    return RedirectResponse(f"{settings.frontend_url}/auth/callback?{query}", status_code=302)

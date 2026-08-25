from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

_DEFAULT_LOCALE = "en"
_LANG_DIR = Path(__file__).resolve().parent.parent / "lang"
_LOCALE_HEADER = "locale"


@lru_cache
def _supported_locales() -> frozenset[str]:
    return frozenset(p.name for p in _LANG_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))


@lru_cache
def _load_catalog(locale: str) -> dict[str, str]:
    try:
        module = import_module(f"app.lang.{locale}.message")
    except ModuleNotFoundError:
        return {}
    return getattr(module, "MESSAGES", {})


def translate(key: str, locale: str, **params: Any) -> str:
    """Look up `key` in `locale`'s catalog (app/lang/{locale}/message.py), falling back to English,
    then to the raw key itself if truly missing, then fill in any {placeholder} params.

    `locale` is always passed explicitly — deliberately no ambient/global state here. Every caller
    already has a natural way to get it: exception handlers and routes have `request` (see
    `request_locale` below), and the one caller that can't reach a Request at all — the arq worker
    sending the password-reset email — has the locale threaded through the job payload instead,
    captured from the original HTTP request that triggered it.
    """
    message = _load_catalog(locale).get(key) or _load_catalog(_DEFAULT_LOCALE).get(key) or key
    return message.format(**params) if params else message


def request_locale(request: Request) -> str:
    """The locale LocaleMiddleware already resolved for this request."""
    return getattr(request.state, "locale", _DEFAULT_LOCALE)


class LocaleMiddleware:
    """Reads the `locale` header (matching the existing Laravel API's own convention — not the
    standard Accept-Language) and validates it against the directories in app/lang/, defaulting to
    English for anything missing or unsupported. Sets request.state.locale for translate() to use.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        raw_locale = request.headers.get(_LOCALE_HEADER)
        request.state.locale = raw_locale if raw_locale in _supported_locales() else _DEFAULT_LOCALE
        await self.app(scope, receive, send)

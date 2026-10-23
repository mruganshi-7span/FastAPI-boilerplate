from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.localization import LocaleMiddleware
from app.core.queue import close_redis_pool

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await close_redis_pool()


def create_app() -> FastAPI:
    # Deliberately not passing debug=settings.app_debug: Starlette's ServerErrorMiddleware ignores
    # registered Exception handlers entirely when debug=True and renders a raw traceback (with local
    # file paths) straight into the HTTP response instead. Our own handler in core/exceptions.py
    # already logs the full traceback server-side — that's the only "debug" behavior we want.
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Reads the `locale` header (matching the existing Laravel API's own convention) and validates
    # it against app/lang/*, setting request.state.locale. translate() (app/core/localization.py)
    # does the actual message lookup, against plain Python dicts in app/lang/{locale}/message.py.
    app.add_middleware(LocaleMiddleware)

    # Only used by Authlib to keep OAuth `state`/`nonce` between /auth/google/login and the
    # callback. `lax` (not `strict`) so the cookie is still sent on Google's top-level redirect back.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=settings.app_env != "local",
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

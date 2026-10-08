from fastapi import APIRouter, Depends

from ....infrastructure.auth.routes import router as auth_router
from ....infrastructure.auth.setup import api_rate_limit_dependency
from ....modules.user.routes import router as users_router

# One rate limit, read from settings, applied to every /api/v1 route.
router = APIRouter(prefix="/v1", dependencies=[Depends(api_rate_limit_dependency)])
router.include_router(users_router, prefix="/users")
router.include_router(auth_router, prefix="/auth")

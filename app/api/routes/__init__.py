from fastapi import APIRouter

from app.api.routes import auth, categories, media, social_auth, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(social_auth.router)
api_router.include_router(users.router)
api_router.include_router(categories.router)
api_router.include_router(media.router)

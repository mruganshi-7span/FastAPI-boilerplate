import asyncio

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

settings = get_settings()

_redis_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


async def get_or_create_redis_pool() -> ArqRedis:
    global _redis_pool

    if _redis_pool is None:
        async with _pool_lock:
            if _redis_pool is None:
                _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool

    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None

from redis.asyncio import Redis, from_url

from app.config import settings

if not settings.redis_url.startswith(("redis://", "rediss://")):
    raise ValueError("Invalid Redis URL scheme. Expected redis:// or rediss://")

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(settings.redis_url, decode_responses=True)
    return _redis


async def ping_redis() -> None:
    redis = await get_redis()
    await redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None

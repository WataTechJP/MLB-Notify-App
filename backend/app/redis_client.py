from redis.asyncio import Redis, from_url

from app.config import settings

REDIS_SOCKET_TIMEOUT_SECONDS = 5

if not settings.redis_url.startswith(("redis://", "rediss://")):
    raise ValueError("Invalid Redis URL scheme. Expected redis:// or rediss://")

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            health_check_interval=30,
        )
    return _redis


async def ping_redis() -> None:
    redis = await get_redis()
    await redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None

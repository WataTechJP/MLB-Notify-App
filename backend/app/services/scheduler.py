import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.event_detector import detect_events

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_http_client: httpx.AsyncClient | None = None


async def _poll_job() -> None:
    """APSchedulerから定期実行されるジョブ"""
    if _http_client is None:
        logger.warning("HTTP client not initialized, skipping poll")
        return
    logger.debug("Polling MLB API... (game_type=%s)", settings.game_type)
    try:
        redis = await get_redis()
        async with AsyncSessionLocal() as db:
            await detect_events(redis, db, _http_client, game_type=settings.game_type)
    except Exception as e:
        logger.error("Poll job error: %s", e, exc_info=True)


def start_scheduler() -> None:
    global _scheduler, _http_client

    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
    )

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _poll_job,
        trigger=IntervalTrigger(seconds=settings.poll_interval_seconds),
        id="mlb_poll",
        name="MLB event polling",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started (interval=%ds, game_type=%s)",
        settings.poll_interval_seconds,
        settings.game_type,
    )


async def stop_scheduler() -> None:
    global _scheduler, _http_client

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    if _http_client:
        await _http_client.aclose()
        _http_client = None

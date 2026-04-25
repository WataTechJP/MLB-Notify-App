import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router
from app.config import settings
from app.database import create_tables
from app.redis_client import close_redis, ping_redis
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
_EXPO_TOKEN_RE = re.compile(r"ExponentPushToken\[[^\]]+\]")


class PushTokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        def _redact(value):
            if isinstance(value, str):
                return _EXPO_TOKEN_RE.sub("ExponentPushToken[redacted]", value)
            if isinstance(value, tuple):
                return tuple(_redact(item) for item in value)
            if isinstance(value, list):
                return [_redact(item) for item in value]
            return value

        record.msg = _redact(record.msg)
        record.args = _redact(record.args)
        return True


def _install_push_token_redaction() -> None:
    token_filter = PushTokenRedactionFilter()
    for target in (
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
        logging.getLogger("uvicorn.error"),
    ):
        for handler in target.handlers:
            handler.addFilter(token_filter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("Starting up MLB notification backend...")
    logger.info(
        "Settings: DEBUG=%s ENABLE_TEST_ENDPOINTS=%s",
        settings.debug,
        settings.enable_test_endpoints,
    )
    logger.info("Initializing database tables...")
    try:
        await create_tables()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)
        raise
    logger.info("Checking Redis connectivity...")
    try:
        await ping_redis()
        logger.info("Redis connectivity verified")
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        raise
    start_scheduler()
    logger.info("Scheduler started")
    yield
    # shutdown
    logger.info("Shutting down...")
    await stop_scheduler()
    await close_redis()


app = FastAPI(
    title="MLB Japanese Player Notification API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.debug else None,
)

_install_push_token_redaction()
app.include_router(router)


@app.get("/api/v1/health", tags=["health"])
async def health():
    return {"status": "ok"}

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router
from app.config import settings
from app.database import create_tables
from app.redis_client import close_redis
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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

app.include_router(router)


@app.get("/api/v1/health", tags=["health"])
async def health():
    return {"status": "ok"}

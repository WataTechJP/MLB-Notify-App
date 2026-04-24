import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

def _normalize_database_url(raw_url: str) -> str:
    """
    DATABASE_URL を SQLAlchemy async 用URLへ正規化する。
    - postgresql+asyncpg://...      -> そのまま
    - postgresql://...              -> postgresql+asyncpg://... に変換
    - postgres://...                -> postgresql+asyncpg://... に変換
    - sqlite+aiosqlite:///...       -> そのまま
    - sqlite:///...                 -> sqlite+aiosqlite:///... に変換
    """
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("sqlite+aiosqlite:///"):
        return raw_url
    if raw_url.startswith("sqlite:///"):
        return raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    raise ValueError(
        "Unsupported DATABASE_URL. Use postgresql://, postgres://, "
        "postgresql+asyncpg://, sqlite:/// or sqlite+aiosqlite:///"
    )

DATABASE_URL = _normalize_database_url(settings.database_url)

# SQLiteのDBファイル用ディレクトリを自動作成
if DATABASE_URL.startswith("sqlite+aiosqlite:///"):
    db_path = DATABASE_URL[len("sqlite+aiosqlite:///"):]
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    engine = create_async_engine(
        DATABASE_URL,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    async with engine.begin() as conn:
        from app.models import user  # noqa: F401 - モデル登録のためインポート
        await conn.run_sync(Base.metadata.create_all)

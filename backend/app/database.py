import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQLiteのみサポート (スキーム検証)
if not settings.database_url.startswith("sqlite+aiosqlite:///"):
    raise ValueError("Only sqlite+aiosqlite:/// scheme is supported for DATABASE_URL")

# SQLiteのDBファイル用ディレクトリを自動作成
db_path = settings.database_url[len("sqlite+aiosqlite:///"):]
os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
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

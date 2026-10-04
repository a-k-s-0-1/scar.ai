"""Database async engine and session management."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database.models import Base

settings = get_settings()

# How long a blocked SQLite writer waits for the lock before giving up.
SQLITE_BUSY_TIMEOUT_MS = 30_000

engine_kwargs: dict[str, Any] = {
    "echo": settings.LOG_LEVEL.upper() == "DEBUG",
    "future": True,
}

# SQLite specific connect args
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL pooling settings
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True


def configure_sqlite(engine: AsyncEngine) -> None:
    """Make a SQLite engine tolerate one writer next to many readers.

    The research loop holds a write transaction open across network calls (source
    search, claim extraction), so with the default rollback journal a read request
    arriving mid-iteration could not acquire a shared lock and failed the whole
    request with ``database is locked`` — a 500 on a plain GET while the user was
    watching a live run. Write-ahead logging lets readers keep reading the last
    committed snapshot while a writer is active, and a busy timeout makes the
    remaining writer-versus-writer contention wait instead of erroring.
    """
    if engine.url.get_backend_name() != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _apply_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()


engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
configure_sqlite(engine)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables if they do not exist (useful for quickstart and tests)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

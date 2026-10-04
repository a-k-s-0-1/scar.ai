"""Regression tests for SQLite read/write contention.

A live run once returned HTTP 500 on ``GET /api/research/{id}/report`` while the
orchestrator held a write transaction open across network calls: with the default
rollback journal the reader could not take its shared lock and failed with
``database is locked``. ``configure_sqlite`` switches the engine to WAL so readers
keep reading the last committed snapshot while a writer is active.
"""

import sqlite3
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database.session import SQLITE_BUSY_TIMEOUT_MS, configure_sqlite


def _async_engine(path: Path, *, read_timeout: float | None = None) -> AsyncEngine:
    connect_args: dict[str, object] = {"check_same_thread": False}
    if read_timeout is not None:
        connect_args["timeout"] = read_timeout
    return create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}", connect_args=connect_args)


@pytest_asyncio.fixture(scope="function")
async def configured_db(tmp_path: Path) -> AsyncGenerator[tuple[AsyncEngine, Path], None]:
    """A file-backed engine that has had the application's SQLite setup applied."""
    path = tmp_path / "configured.db"
    engine = _async_engine(path)
    configure_sqlite(engine)

    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, blob TEXT)")
        await conn.exec_driver_sql("INSERT INTO probe (id, blob) VALUES (1, 'committed')")

    yield engine, path
    await engine.dispose()


@pytest.mark.asyncio
async def test_configure_enables_wal_and_busy_timeout(
    configured_db: tuple[AsyncEngine, Path],
) -> None:
    engine, _path = configured_db

    async with engine.connect() as conn:
        journal_mode = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar()
        busy_timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar()

    assert str(journal_mode).lower() == "wal"
    assert int(busy_timeout) == SQLITE_BUSY_TIMEOUT_MS


@pytest.mark.asyncio
async def test_reader_succeeds_while_writer_holds_exclusive_lock(
    configured_db: tuple[AsyncEngine, Path],
) -> None:
    engine, path = configured_db

    # A foreign connection (not from our pool) grabbing the strongest write lock.
    writer = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT INTO probe (id, blob) VALUES (2, 'uncommitted')")

        async with engine.connect() as reader:
            rows = (await reader.exec_driver_sql("SELECT id FROM probe ORDER BY id")).scalars().all()

        # The reader is served from the last committed snapshot, not blocked.
        assert rows == [1]
    finally:
        writer.rollback()
        writer.close()


@pytest.mark.asyncio
async def test_without_configure_a_reader_is_blocked(tmp_path: Path) -> None:
    """Documents why the pragmas exist: the unconfigured engine does fail."""
    path = tmp_path / "vanilla.db"
    engine = _async_engine(path, read_timeout=0.2)  # short wait, so failure is fast

    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, blob TEXT)")
        await conn.exec_driver_sql("INSERT INTO probe (id, blob) VALUES (1, 'committed')")

    writer = sqlite3.connect(path, isolation_level=None)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT INTO probe (id, blob) VALUES (2, 'uncommitted')")

        with pytest.raises(OperationalError, match="locked"):
            async with engine.connect() as reader:
                await reader.exec_driver_sql("SELECT id FROM probe")
    finally:
        writer.rollback()
        writer.close()
        await engine.dispose()

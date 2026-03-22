"""Tests for SQLite connection management."""

from pathlib import Path

import pytest

from breqy.storage.sqlite.connection import create_connection


@pytest.mark.asyncio
async def test_create_connection(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    assert conn is not None
    # Verify WAL mode
    cursor = await conn.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row[0] == "wal"
    await conn.close()


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    cursor = await conn.execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    assert row[0] == 1
    await conn.close()


@pytest.mark.asyncio
async def test_busy_timeout_set(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    cursor = await conn.execute("PRAGMA busy_timeout")
    row = await cursor.fetchone()
    assert row[0] == 5000
    await conn.close()

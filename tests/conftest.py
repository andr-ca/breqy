"""
Shared pytest fixtures for all Breqy tests.

Provides:
  - tmp_dir       — isolated temporary directory (Path)
  - db_path       — path to a SQLite database file inside tmp_dir
  - db_connection — async aiosqlite.Connection to db_path with schema applied (auto-closed)
  - socket_path   — path reserved for a Unix domain socket inside tmp_dir
"""
from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio

from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Return an isolated temporary directory for the test."""
    return tmp_path


@pytest.fixture()
def db_path(tmp_dir: Path) -> Path:
    """Return a Path inside tmp_dir for a SQLite database file."""
    return tmp_dir / "test.db"


@pytest_asyncio.fixture()
async def db_connection(db_path: Path) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Open a fully-configured aiosqlite connection (WAL, FK, schema applied)."""
    conn = await create_connection(str(db_path))
    await run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture()
def socket_path(tmp_dir: Path) -> Path:
    """Return a Path inside tmp_dir reserved for a Unix domain socket."""
    return tmp_dir / "engine.sock"

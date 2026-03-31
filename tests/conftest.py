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


@pytest.fixture()
def fake_agent_dir(tmp_path: Path) -> Path:
    """Create a minimal agent directory with agent.yaml and persona.md.

    Returns the directory path, suitable for ``load_agent_config(str(path))``.
    """
    agent_dir = tmp_path / "agents" / "breqy"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(
        "id: breqy\n"
        "name: Breqy\n"
        "display_name: Breqy\n"
        "provider: copilot\n"
        "model: gpt-4o\n"
        "persona_file: persona.md\n"
        "autonomy_level: supervised\n"
    )
    (agent_dir / "persona.md").write_text("You are Breqy.\n")
    return agent_dir

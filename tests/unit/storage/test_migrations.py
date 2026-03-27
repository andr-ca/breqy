"""Tests for SQLite schema migrations."""

from pathlib import Path

import pytest

from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations

EXPECTED_TABLES = {
    "sessions",
    "participants",
    "messages",
    "tasks",
    "tool_invocations",
    "approval_requests",
    "approval_decisions",
    "events",
    "memory_records",
    "memory_promotions",
    "schema_version",
}


@pytest.mark.asyncio
async def test_run_migrations_creates_tables(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in await cursor.fetchall()}
    assert EXPECTED_TABLES.issubset(tables)
    await conn.close()


@pytest.mark.asyncio
async def test_migrations_are_idempotent(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)
    await run_migrations(conn)  # Must not raise
    await conn.close()


@pytest.mark.asyncio
async def test_schema_version_recorded(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("SELECT version FROM schema_version")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 2
    await conn.close()


@pytest.mark.asyncio
async def test_sessions_table_columns(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("PRAGMA table_info(sessions)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols == {"id", "status", "primary_agent_id", "workspace_paths", "created_at", "updated_at"}
    await conn.close()


@pytest.mark.asyncio
async def test_events_table_columns(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("PRAGMA table_info(events)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols == {
        "event_id", "event_type", "schema_version",
        "session_id", "agent_id", "correlation_id", "timestamp", "payload",
    }
    await conn.close()


@pytest.mark.asyncio
async def test_memory_records_table_columns(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("PRAGMA table_info(memory_records)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols == {
        "id",
        "scope",
        "session_id",
        "agent_id",
        "kind",
        "source",
        "content",
        "tags",
        "task_id",
        "approval_id",
        "artifact_id",
        "linked_event_id",
        "promotion_id",
        "created_at",
        "updated_at",
    }
    await conn.close()


@pytest.mark.asyncio
async def test_memory_promotions_table_columns(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("PRAGMA table_info(memory_promotions)")
    cols = {row[1] for row in await cursor.fetchall()}
    assert cols == {
        "id",
        "source_record_id",
        "target_record_id",
        "source_session_id",
        "proposing_agent_id",
        "approval_id",
        "status",
        "source_scope",
        "target_scope",
        "created_at",
        "updated_at",
    }
    await conn.close()


@pytest.mark.asyncio
async def test_memory_filter_indexes_exist(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    cursor = await conn.execute("PRAGMA index_list(memory_records)")
    indexes = {row[1] for row in await cursor.fetchall()}
    assert {
        "idx_memory_records_scope",
        "idx_memory_records_session",
        "idx_memory_records_agent",
        "idx_memory_records_task",
        "idx_memory_records_approval",
        "idx_memory_records_artifact",
        "idx_memory_records_linked_event",
        "idx_memory_records_promotion",
    }.issubset(indexes)
    await conn.close()

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
    "approval_grants",
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
    assert row[0] == 3
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


@pytest.mark.asyncio
async def test_run_migrations_upgrades_existing_approval_tables(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY
        );
        CREATE TABLE approval_requests (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            agent_id TEXT NOT NULL,
            tool_invocation_id TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE approval_decisions (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            granted INTEGER NOT NULL,
            extend_to_session INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            decided_at TEXT NOT NULL
        );
        """
    )
    await conn.execute("INSERT INTO sessions (id) VALUES ('ses_1')")
    await conn.execute(
        """
        INSERT INTO approval_requests
            (id, session_id, agent_id, tool_invocation_id, description, status, created_at)
        VALUES
            ('apr_old', 'ses_1', 'agt_1', 'inv_1', 'Browser submit on google.com', 'granted', '2026-01-01T00:00:00+00:00')
        """
    )
    await conn.execute(
        """
        INSERT INTO approval_decisions
            (id, request_id, granted, extend_to_session, reason, decided_at)
        VALUES
            ('apd_old', 'apr_old', 1, 1, '', '2026-01-01T00:00:00+00:00')
        """
    )
    await conn.commit()

    await run_migrations(conn)

    requests_cursor = await conn.execute("PRAGMA table_info(approval_requests)")
    request_columns = {row[1] for row in await requests_cursor.fetchall()}
    assert "grant_key" in request_columns

    decisions_cursor = await conn.execute("PRAGMA table_info(approval_decisions)")
    decision_columns = {row[1] for row in await decisions_cursor.fetchall()}
    assert "grant_scope" in decision_columns

    decision_cursor = await conn.execute(
        "SELECT grant_scope FROM approval_decisions WHERE id = 'apd_old'"
    )
    decision_row = await decision_cursor.fetchone()
    assert decision_row is not None
    assert decision_row[0] == "session"

    request_cursor = await conn.execute(
        "SELECT grant_key FROM approval_requests WHERE id = 'apr_old'"
    )
    request_row = await request_cursor.fetchone()
    assert request_row is not None
    assert request_row[0] == "Browser submit on google.com"

    grants_cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='approval_grants'"
    )
    assert await grants_cursor.fetchone() is not None

    backfill_cursor = await conn.execute(
        """
        SELECT session_id, grant_key, scope
        FROM approval_grants
        WHERE session_id = 'ses_1'
        """
    )
    backfill_row = await backfill_cursor.fetchone()
    assert tuple(backfill_row) == ("ses_1", "Browser submit on google.com", "session")

    await conn.close()


@pytest.mark.asyncio
async def test_run_migrations_backfills_forever_grants_with_null_session_id(db_path: Path) -> None:
    conn = await create_connection(str(db_path))
    await conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY
        );
        CREATE TABLE approval_requests (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            agent_id TEXT NOT NULL,
            tool_invocation_id TEXT NOT NULL,
            description TEXT NOT NULL,
            grant_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE approval_decisions (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            granted INTEGER NOT NULL,
            grant_scope TEXT NOT NULL DEFAULT 'once',
            reason TEXT NOT NULL DEFAULT '',
            decided_at TEXT NOT NULL
        );
        """
    )
    await conn.execute("INSERT INTO sessions (id) VALUES ('ses_1')")
    await conn.execute(
        """
        INSERT INTO approval_requests
            (id, session_id, agent_id, tool_invocation_id, description, grant_key, status, created_at)
        VALUES
            ('apr_forever', 'ses_1', 'agt_1', 'inv_2', 'Browser extract on google.com', 'browser:extract:google.com', 'granted', '2026-01-01T00:00:00+00:00')
        """
    )
    await conn.execute(
        """
        INSERT INTO approval_decisions
            (id, request_id, granted, grant_scope, reason, decided_at)
        VALUES
            ('apd_forever', 'apr_forever', 1, 'forever', '', '2026-01-01T00:00:00+00:00')
        """
    )
    await conn.commit()

    await run_migrations(conn)

    forever_cursor = await conn.execute(
        """
        SELECT session_id, grant_key, scope
        FROM approval_grants
        WHERE grant_key = 'browser:extract:google.com'
        """
    )
    forever_row = await forever_cursor.fetchone()
    assert tuple(forever_row) == (None, "browser:extract:google.com", "forever")
    await conn.close()


@pytest.mark.asyncio
async def test_run_migrations_is_idempotent_even_with_duplicate_grants(db_path: Path) -> None:
    """SCHEMA_V3 must not fail when approval_grants already contains duplicates.

    The UNIQUE index is created in _upgrade_approval_tables() *after* the dedup
    step, so running migrations against a DB that already has duplicate rows must
    succeed (deduplicate first, then create the index).
    """
    conn = await create_connection(str(db_path))
    # Minimal pre-existing schema without the unique index
    await conn.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY);
        CREATE TABLE approval_grants (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            grant_key TEXT NOT NULL,
            scope TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_approval_grants_session_key
            ON approval_grants(session_id, grant_key);
        """
    )
    # Insert two duplicate rows (same logical key)
    await conn.executemany(
        "INSERT INTO approval_grants (id, session_id, grant_key, scope, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("apg_1", "ses_1", "browser:click:example.com", "session", "2026-01-01T00:00:00"),
            ("apg_2", "ses_1", "browser:click:example.com", "session", "2026-01-01T00:00:01"),
        ],
    )
    await conn.commit()

    # Must not raise even though duplicates exist before the unique index is created
    await run_migrations(conn)

    # Only one row should survive deduplication
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM approval_grants WHERE grant_key = 'browser:click:example.com'"
    )
    row = await cursor.fetchone()
    assert row[0] == 1

    # Unique index must exist after migration
    idx_cursor = await conn.execute("PRAGMA index_list(approval_grants)")
    index_names = {r[1] for r in await idx_cursor.fetchall()}
    assert "idx_approval_grants_unique" in index_names

    await conn.close()

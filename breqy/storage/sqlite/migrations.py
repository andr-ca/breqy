"""SQLite schema DDL and migration runner.

All tables use IF NOT EXISTS so running migrations is idempotent.
"""

import aiosqlite

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    primary_agent_id TEXT NOT NULL,
    workspace_paths TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    left_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_participants_session ON participants(session_id);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    parent_id TEXT,
    agent_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);

CREATE TABLE IF NOT EXISTS tool_invocations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    approval_id TEXT,
    summary TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_invocations_session ON tool_invocations(session_id);

CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    tool_invocation_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approval_requests(session_id);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES approval_requests(id),
    granted INTEGER NOT NULL,
    extend_to_session INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(session_id, timestamp);

CREATE TABLE IF NOT EXISTS memory_records (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    session_id TEXT REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    task_id TEXT,
    approval_id TEXT,
    artifact_id TEXT,
    linked_event_id TEXT,
    promotion_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_records_scope ON memory_records(scope);
CREATE INDEX IF NOT EXISTS idx_memory_records_session ON memory_records(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_records_agent ON memory_records(agent_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_task ON memory_records(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_approval ON memory_records(approval_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_artifact ON memory_records(artifact_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_linked_event ON memory_records(linked_event_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_promotion ON memory_records(promotion_id);

CREATE TABLE IF NOT EXISTS memory_promotions (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL REFERENCES memory_records(id),
    target_record_id TEXT REFERENCES memory_records(id),
    source_session_id TEXT NOT NULL REFERENCES sessions(id),
    proposing_agent_id TEXT NOT NULL,
    approval_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    source_scope TEXT NOT NULL DEFAULT 'session',
    target_scope TEXT NOT NULL DEFAULT 'global',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_promotions_source_record ON memory_promotions(source_record_id);
CREATE INDEX IF NOT EXISTS idx_memory_promotions_status ON memory_promotions(status);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


async def run_migrations(conn: aiosqlite.Connection) -> None:
    """Run schema migrations. Safe to call multiple times (idempotent)."""
    await conn.executescript(SCHEMA_V2)
    await conn.execute(
        "INSERT INTO schema_version (version) VALUES (?) ON CONFLICT(version) DO NOTHING",
        (2,),
    )
    await conn.execute("DELETE FROM schema_version WHERE version <> ?", (2,))
    await conn.commit()

"""SQLite implementation of SessionRepository."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session
from breqy.storage.interfaces import SessionRepository


class SqliteSessionRepository(SessionRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, session: Session) -> None:
        await self._conn.execute(
            """INSERT INTO sessions
               (id, status, primary_agent_id, workspace_paths, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.status.value,
                session.primary_agent_id,
                json.dumps(session.workspace_paths),
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get(self, session_id: str) -> Session | None:
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    async def list_active(self) -> list[Session]:
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE status = ? ORDER BY updated_at DESC",
            (SessionStatus.ACTIVE.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        now = datetime.now(UTC).isoformat()
        await self._conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, session_id),
        )
        await self._conn.commit()

    async def update_timestamp(self, session_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        await self._conn.commit()

    async def update_workspace_paths(
        self, session_id: str, paths: list[str]
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self._conn.execute(
            "UPDATE sessions SET workspace_paths = ?, updated_at = ? WHERE id = ?",
            (json.dumps(paths), now, session_id),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_session(row: aiosqlite.Row) -> Session:
        return Session(
            id=row["id"],
            status=SessionStatus(row["status"]),
            primary_agent_id=row["primary_agent_id"],
            workspace_paths=json.loads(row["workspace_paths"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

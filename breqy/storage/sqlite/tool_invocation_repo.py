"""SQLite implementation of ToolInvocationRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from breqy.domain.enums import ToolStatus
from breqy.domain.models import ToolInvocation
from breqy.storage.interfaces import ToolInvocationRepository


class SqliteToolInvocationRepository(ToolInvocationRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, invocation: ToolInvocation) -> None:
        await self._conn.execute(
            """INSERT INTO tool_invocations
               (id, session_id, agent_id, tool_name, arguments, status,
                result, error, approval_id, summary, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invocation.id,
                invocation.session_id,
                invocation.agent_id,
                invocation.tool_name,
                json.dumps(invocation.arguments),
                invocation.status.value,
                json.dumps(invocation.result) if invocation.result is not None else None,
                invocation.error,
                invocation.approval_id,
                invocation.summary,
                invocation.started_at.isoformat(),
                invocation.completed_at.isoformat() if invocation.completed_at else None,
            ),
        )
        await self._conn.commit()

    async def get(self, invocation_id: str) -> ToolInvocation | None:
        cursor = await self._conn.execute(
            "SELECT * FROM tool_invocations WHERE id = ?", (invocation_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_tool_invocation(row)

    async def list_by_session(self, session_id: str) -> list[ToolInvocation]:
        cursor = await self._conn.execute(
            """SELECT * FROM tool_invocations
               WHERE session_id = ?
               ORDER BY started_at DESC""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_tool_invocation(row) for row in rows]

    async def update_result(
        self,
        invocation_id: str,
        status: ToolStatus,
        result: dict[str, Any] | None,
        error: str,
        summary: str,
        approval_id: str | None = None,
    ) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """UPDATE tool_invocations
               SET status = ?, result = ?, error = ?, approval_id = ?,
                   summary = ?, completed_at = ?
               WHERE id = ?""",
            (
                status.value,
                json.dumps(result) if result is not None else None,
                error,
                approval_id,
                summary,
                completed_at,
                invocation_id,
            ),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_tool_invocation(row: aiosqlite.Row) -> ToolInvocation:
        return ToolInvocation(
            id=row["id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments"]),
            status=ToolStatus(row["status"]),
            approval_id=row["approval_id"],
            result=json.loads(row["result"]) if row["result"] is not None else None,
            error=row["error"],
            summary=row["summary"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"] is not None
                else None
            ),
        )

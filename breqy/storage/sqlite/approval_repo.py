"""SQLite implementation of ApprovalRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest
from breqy.storage.interfaces import ApprovalRepository


class SqliteApprovalRepository(ApprovalRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create_request(self, request: ApprovalRequest) -> None:
        await self._conn.execute(
            """INSERT INTO approval_requests
               (id, session_id, agent_id, tool_invocation_id, description, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                request.id,
                request.session_id,
                request.agent_id,
                request.tool_invocation_id,
                request.description,
                request.status.value,
                request.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def create_decision(self, decision: ApprovalDecision) -> None:
        await self._conn.execute(
            """INSERT INTO approval_decisions
               (id, request_id, granted, extend_to_session, reason, decided_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                decision.id,
                decision.request_id,
                1 if decision.granted else 0,
                1 if decision.extend_to_session else 0,
                decision.reason,
                decision.decided_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get_request(self, request_id: str) -> ApprovalRequest | None:
        cursor = await self._conn.execute(
            "SELECT * FROM approval_requests WHERE id = ?", (request_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_request(row)

    async def get_pending_by_session(self, session_id: str) -> list[ApprovalRequest]:
        cursor = await self._conn.execute(
            """SELECT * FROM approval_requests
               WHERE session_id = ? AND status = ?
               ORDER BY created_at ASC""",
            (session_id, ApprovalStatus.PENDING.value),
        )
        rows = await cursor.fetchall()
        return [self._row_to_request(row) for row in rows]

    async def update_request_status(
        self, request_id: str, status: ApprovalStatus
    ) -> None:
        await self._conn.execute(
            "UPDATE approval_requests SET status = ? WHERE id = ?",
            (status.value, request_id),
        )
        await self._conn.commit()

    async def get_session_grants(self, session_id: str) -> list[ApprovalDecision]:
        """Return all extend_to_session=True decisions for a given session."""
        cursor = await self._conn.execute(
            """SELECT d.* FROM approval_decisions d
               JOIN approval_requests r ON r.id = d.request_id
               WHERE r.session_id = ? AND d.extend_to_session = 1
               ORDER BY d.decided_at ASC""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_decision(row) for row in rows]

    @staticmethod
    def _row_to_request(row: aiosqlite.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=row["id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            tool_invocation_id=row["tool_invocation_id"],
            description=row["description"],
            status=ApprovalStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_decision(row: aiosqlite.Row) -> ApprovalDecision:
        return ApprovalDecision(
            id=row["id"],
            request_id=row["request_id"],
            granted=bool(row["granted"]),
            extend_to_session=bool(row["extend_to_session"]),
            reason=row["reason"],
            decided_at=datetime.fromisoformat(row["decided_at"]),
        )

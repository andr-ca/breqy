"""SQLite implementation of ApprovalRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.enums import ApprovalGrantScope, ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalGrant, ApprovalRequest
from breqy.storage.interfaces import ApprovalRepository


class SqliteApprovalRepository(ApprovalRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create_request(self, request: ApprovalRequest) -> None:
        await self._conn.execute(
            """INSERT INTO approval_requests
               (id, session_id, agent_id, tool_invocation_id, description, grant_key, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request.id,
                request.session_id,
                request.agent_id,
                request.tool_invocation_id,
                request.description,
                request.grant_key,
                request.status.value,
                request.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def create_decision(self, decision: ApprovalDecision) -> None:
        await self._conn.execute(
            """INSERT INTO approval_decisions
               (id, request_id, granted, grant_scope, reason, decided_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                decision.id,
                decision.request_id,
                1 if decision.granted else 0,
                decision.grant_scope.value,
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
        """Return all session-scoped decisions for a given session."""
        cursor = await self._conn.execute(
            """SELECT d.* FROM approval_decisions d
               JOIN approval_requests r ON r.id = d.request_id
               WHERE r.session_id = ? AND d.grant_scope = ?
               ORDER BY d.decided_at ASC""",
            (session_id, ApprovalGrantScope.SESSION.value),
        )
        rows = await cursor.fetchall()
        return [self._row_to_decision(row) for row in rows]

    async def create_grant(self, grant: ApprovalGrant) -> None:
        await self._conn.execute(
            """INSERT INTO approval_grants
               (id, session_id, grant_key, scope, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                grant.id,
                grant.session_id,
                grant.grant_key,
                grant.scope.value,
                grant.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def has_grant(self, *, session_id: str, grant_key: str) -> bool:
        cursor = await self._conn.execute(
            """SELECT 1 FROM approval_grants
               WHERE grant_key = ?
                 AND (scope = ? OR (scope = ? AND session_id = ?))
               LIMIT 1""",
            (
                grant_key,
                ApprovalGrantScope.FOREVER.value,
                ApprovalGrantScope.SESSION.value,
                session_id,
            ),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_grants(self, session_id: str | None = None) -> list[ApprovalGrant]:
        if session_id is None:
            cursor = await self._conn.execute(
                "SELECT * FROM approval_grants WHERE scope = ? ORDER BY created_at ASC",
                (ApprovalGrantScope.FOREVER.value,),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM approval_grants WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_grant(row) for row in rows]

    @staticmethod
    def _row_to_request(row: aiosqlite.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=row["id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            tool_invocation_id=row["tool_invocation_id"],
            description=row["description"],
            grant_key=row["grant_key"],
            status=ApprovalStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_decision(row: aiosqlite.Row) -> ApprovalDecision:
        return ApprovalDecision(
            id=row["id"],
            request_id=row["request_id"],
            granted=bool(row["granted"]),
            grant_scope=ApprovalGrantScope(row["grant_scope"]),
            reason=row["reason"],
            decided_at=datetime.fromisoformat(row["decided_at"]),
        )

    @staticmethod
    def _row_to_grant(row: aiosqlite.Row) -> ApprovalGrant:
        return ApprovalGrant(
            id=row["id"],
            session_id=row["session_id"],
            grant_key=row["grant_key"],
            scope=ApprovalGrantScope(row["scope"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

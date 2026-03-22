"""SQLite implementation of MessageRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.enums import MessageRole
from breqy.domain.models import Message
from breqy.storage.interfaces import MessageRepository


class SqliteMessageRepository(MessageRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, message: Message) -> None:
        await self._conn.execute(
            """INSERT INTO messages (id, session_id, role, content, agent_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                message.id,
                message.session_id,
                message.role.value,
                message.content,
                message.agent_id,
                message.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def list_by_session(
        self,
        session_id: str,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[Message]:
        if before:
            cursor = await self._conn.execute(
                """SELECT * FROM messages WHERE session_id = ? AND created_at < ?
                   ORDER BY created_at ASC LIMIT ?""",
                (session_id, before.isoformat(), limit),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT * FROM messages WHERE session_id = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (session_id, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _row_to_message(row: aiosqlite.Row) -> Message:
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            agent_id=row["agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

"""SQLite implementation of ParticipantRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.models import Participant
from breqy.storage.interfaces import ParticipantRepository


class SqliteParticipantRepository(ParticipantRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, participant: Participant) -> None:
        await self._conn.execute(
            """INSERT INTO participants (id, session_id, agent_id, joined_at, left_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                participant.id,
                participant.session_id,
                participant.agent_id,
                participant.joined_at.isoformat(),
                participant.left_at.isoformat() if participant.left_at else None,
            ),
        )
        await self._conn.commit()

    async def get(self, participant_id: str) -> Participant | None:
        cursor = await self._conn.execute(
            "SELECT * FROM participants WHERE id = ?", (participant_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_participant(row)

    async def list_by_session(self, session_id: str) -> list[Participant]:
        cursor = await self._conn.execute(
            "SELECT * FROM participants WHERE session_id = ? ORDER BY joined_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_participant(row) for row in rows]

    async def get_active_by_session(self, session_id: str) -> list[Participant]:
        cursor = await self._conn.execute(
            "SELECT * FROM participants WHERE session_id = ? AND left_at IS NULL ORDER BY joined_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_participant(row) for row in rows]

    async def get_by_agent_and_session(
        self, agent_id: str, session_id: str
    ) -> Participant | None:
        cursor = await self._conn.execute(
            "SELECT * FROM participants WHERE agent_id = ? AND session_id = ? ORDER BY joined_at DESC LIMIT 1",
            (agent_id, session_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_participant(row)

    async def set_left_at(self, participant_id: str, left_at: datetime) -> None:
        await self._conn.execute(
            "UPDATE participants SET left_at = ? WHERE id = ?",
            (left_at.isoformat(), participant_id),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_participant(row: aiosqlite.Row) -> Participant:
        return Participant(
            id=row["id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            joined_at=datetime.fromisoformat(row["joined_at"]),
            left_at=datetime.fromisoformat(row["left_at"]) if row["left_at"] else None,
        )

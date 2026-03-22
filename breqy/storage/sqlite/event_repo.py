"""SQLite implementation of EventRepository (append-only)."""

from __future__ import annotations

import json

import aiosqlite

from breqy.domain.events import Event, deserialize_event
from breqy.storage.interfaces import EventRepository


class SqliteEventRepository(EventRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def append(self, event: Event) -> None:
        # Store all event-type-specific fields as payload
        payload = event.model_dump(
            exclude={
                "event_id",
                "event_type",
                "schema_version",
                "session_id",
                "agent_id",
                "correlation_id",
                "timestamp",
            }
        )
        await self._conn.execute(
            """INSERT INTO events
               (event_id, event_type, schema_version, session_id,
                agent_id, correlation_id, timestamp, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.event_type.value,
                event.schema_version,
                event.session_id,
                event.agent_id,
                event.correlation_id,
                event.timestamp.isoformat(),
                json.dumps(payload, default=str),
            ),
        )
        await self._conn.commit()

    async def list_by_session(
        self, session_id: str, limit: int = 100, after_event_id: str = ""
    ) -> list[Event]:
        if after_event_id:
            cursor = await self._conn.execute(
                "SELECT timestamp FROM events WHERE event_id = ?", (after_event_id,)
            )
            ref_row = await cursor.fetchone()
            if ref_row is None:
                return []
            cursor = await self._conn.execute(
                """SELECT * FROM events WHERE session_id = ? AND timestamp > ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (session_id, ref_row["timestamp"], limit),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT * FROM events WHERE session_id = ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (session_id, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: aiosqlite.Row) -> Event:
        payload = json.loads(row["payload"])
        data = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "schema_version": row["schema_version"],
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "correlation_id": row["correlation_id"],
            "timestamp": row["timestamp"],
            **payload,
        }
        return deserialize_event(data)

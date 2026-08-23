"""SQLite implementation of TaskRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite

from breqy.domain.enums import TaskStatus
from breqy.domain.models import Task
from breqy.storage.interfaces import TaskRepository


class SqliteTaskRepository(TaskRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, task: Task) -> None:
        await self._conn.execute(
            """INSERT INTO tasks
               (id, session_id, title, description, status, parent_id,
                agent_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.session_id,
                task.title,
                task.description,
                task.status.value,
                task.parent_id,
                task.agent_id,
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get(self, task_id: str) -> Task | None:
        cursor = await self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    async def list_by_session(self, session_id: str) -> list[Task]:
        cursor = await self._conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        now = datetime.now(UTC).isoformat()
        await self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, task_id),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_task(row: aiosqlite.Row) -> Task:
        return Task(
            id=row["id"],
            session_id=row["session_id"],
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            parent_id=row["parent_id"],
            agent_id=row["agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

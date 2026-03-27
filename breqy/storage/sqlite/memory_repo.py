"""SQLite implementation of MemoryRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from breqy.domain.enums import MemoryPromotionStatus, MemoryRecordKind, MemoryScope
from breqy.domain.models import MemoryPromotion, MemoryRecord
from breqy.storage.interfaces import MemoryRepository


class SqliteMemoryRepository(MemoryRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create_record(self, record: MemoryRecord) -> None:
        await self._conn.execute(
            """INSERT INTO memory_records
               (id, scope, session_id, agent_id, kind, source, content, tags,
                task_id, approval_id, artifact_id, linked_event_id, promotion_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.scope.value,
                record.session_id,
                record.agent_id,
                record.kind.value,
                record.source,
                record.content,
                json.dumps(record.tags),
                record.task_id,
                record.approval_id,
                record.artifact_id,
                record.linked_event_id,
                record.promotion_id,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get_record(self, record_id: str) -> MemoryRecord | None:
        cursor = await self._conn.execute(
            "SELECT * FROM memory_records WHERE id = ?",
            (record_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    async def list_records(
        self,
        scope: MemoryScope,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
        promotion_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        if scope == MemoryScope.SESSION and session_id is None:
            raise ValueError("session scope requires session_id")
        if scope == MemoryScope.GLOBAL and session_id is not None:
            raise ValueError("global scope does not accept session_id")

        conditions = ["scope = ?"]
        params: list[object] = [scope.value]

        if scope == MemoryScope.SESSION:
            conditions.append("session_id = ?")
            params.append(session_id)

        if agent_id is not None:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        metadata_filters = {
            "task_id": task_id,
            "approval_id": approval_id,
            "artifact_id": artifact_id,
            "linked_event_id": linked_event_id,
            "promotion_id": promotion_id,
        }
        for column, value in metadata_filters.items():
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)

        if tags:
            for tag in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        query = (
            "SELECT * FROM memory_records WHERE "
            + " AND ".join(conditions)
            + " ORDER BY created_at ASC LIMIT ?"
        )
        params.append(limit)
        cursor = await self._conn.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def update_record_promotion(
        self,
        record_id: str,
        promotion_id: str | None,
    ) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE memory_records SET promotion_id = ?, updated_at = ? WHERE id = ?",
            (promotion_id, updated_at, record_id),
        )
        await self._conn.commit()

    async def create_promotion(self, promotion: MemoryPromotion) -> None:
        await self._conn.execute(
            """INSERT INTO memory_promotions
               (id, source_record_id, target_record_id, source_session_id,
                proposing_agent_id, approval_id, status, source_scope,
                target_scope, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                promotion.id,
                promotion.source_record_id,
                promotion.target_record_id,
                promotion.source_session_id,
                promotion.proposing_agent_id,
                promotion.approval_id,
                promotion.status.value,
                promotion.source_scope.value,
                promotion.target_scope.value,
                promotion.created_at.isoformat(),
                promotion.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get_promotion(self, promotion_id: str) -> MemoryPromotion | None:
        cursor = await self._conn.execute(
            "SELECT * FROM memory_promotions WHERE id = ?",
            (promotion_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_promotion(row)

    async def update_promotion_state(
        self,
        promotion_id: str,
        status: MemoryPromotionStatus,
        target_record_id: str | None = None,
    ) -> None:
        if status == MemoryPromotionStatus.APPROVED and target_record_id is None:
            raise ValueError("approved promotions require target_record_id")

        updated_at = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """UPDATE memory_promotions
               SET status = ?, target_record_id = COALESCE(?, target_record_id), updated_at = ?
               WHERE id = ?""",
            (status.value, target_record_id, updated_at, promotion_id),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            scope=MemoryScope(row["scope"]),
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            kind=MemoryRecordKind(row["kind"]),
            source=row["source"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            task_id=row["task_id"],
            approval_id=row["approval_id"],
            artifact_id=row["artifact_id"],
            linked_event_id=row["linked_event_id"],
            promotion_id=row["promotion_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_promotion(row: aiosqlite.Row) -> MemoryPromotion:
        return MemoryPromotion(
            id=row["id"],
            source_record_id=row["source_record_id"],
            target_record_id=row["target_record_id"],
            source_session_id=row["source_session_id"],
            proposing_agent_id=row["proposing_agent_id"],
            approval_id=row["approval_id"],
            status=MemoryPromotionStatus(row["status"]),
            source_scope=MemoryScope(row["source_scope"]),
            target_scope=MemoryScope(row["target_scope"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

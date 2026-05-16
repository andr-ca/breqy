from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

import structlog

from breqy.domain.enums import AutonomyLevel, MemoryRecordKind, MemoryScope
from breqy.domain.ids import generate_prefixed_id
from breqy.memory.contracts import AgentPrivateMemoryStore, PrivateMemoryRecord
from breqy.memory.service import MemoryService
from breqy.tools.executor import ToolExecutor, ToolResult

logger = structlog.get_logger(__name__)


class MemorySearchTool(ToolExecutor):
    name = "mcp.memory.n--search"
    description = "Search engine or private memory through the mediated memory interface"
    input_schema = {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["session", "global", "private"]},
            "session_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "query": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "task_id": {"type": "string"},
            "approval_id": {"type": "string"},
            "artifact_id": {"type": "string"},
            "linked_event_id": {"type": "string"},
            "promotion_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["scope", "agent_id"],
    }

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        private_memory_store: AgentPrivateMemoryStore | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._private_memory_store = private_memory_store

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        scope = _parse_scope(arguments.get("scope"))
        if scope is None:
            return _missing_or_invalid("scope")

        execution_context = _parse_execution_context(arguments)

        agent_id = execution_context.get("agent_id") or _parse_required_string(arguments, "agent_id")
        if agent_id is None:
            return _missing_or_invalid("agent_id")

        query = str(arguments.get("query", ""))
        limit = _parse_limit(arguments.get("limit", 10))
        if limit is None:
            return ToolResult(success=False, error=f"Invalid limit value: {arguments.get('limit')}")

        if scope == "private":
            if self._private_memory_store is None:
                return ToolResult(
                    success=False,
                    error="private memory runtime wiring is deferred until Phase 8",
                )
            private_records = await self._private_memory_store.search(
                agent_id=agent_id,
                query=query,
                limit=limit,
            )
            return ToolResult(
                success=True,
                output={"scope": "private", "records": [asdict(record) for record in private_records]},
                summary=f"Found {len(private_records)} private memory record(s)",
            )

        if scope == "session":
            session_id = execution_context.get("session_id") or _parse_required_string(arguments, "session_id")
            if session_id is None:
                return _missing_or_invalid("session_id")
            records = await self._memory_service.search_records(
                scope=MemoryScope.SESSION,
                session_id=session_id,
                agent_id=agent_id,
                query=query,
                tags=_parse_tags(arguments.get("tags")),
                task_id=_parse_optional_string(arguments.get("task_id")),
                approval_id=_parse_optional_string(arguments.get("approval_id")),
                artifact_id=_parse_optional_string(arguments.get("artifact_id")),
                linked_event_id=_parse_optional_string(arguments.get("linked_event_id")),
                promotion_id=_parse_optional_string(arguments.get("promotion_id")),
                limit=limit,
            )
            return ToolResult(
                success=True,
                output={"scope": MemoryScope.SESSION.value, "records": [record.model_dump(mode="json") for record in records]},
                summary=f"Found {len(records)} session memory record(s)",
            )

        records = await self._memory_service.search_records(
            scope=MemoryScope.GLOBAL,
            session_id=_parse_optional_string(arguments.get("session_id")),
            agent_id=agent_id,
            query=query,
            tags=_parse_tags(arguments.get("tags")),
            task_id=_parse_optional_string(arguments.get("task_id")),
            approval_id=_parse_optional_string(arguments.get("approval_id")),
            artifact_id=_parse_optional_string(arguments.get("artifact_id")),
            linked_event_id=_parse_optional_string(arguments.get("linked_event_id")),
            promotion_id=_parse_optional_string(arguments.get("promotion_id")),
            limit=limit,
        )
        return ToolResult(
            success=True,
            output={"scope": MemoryScope.GLOBAL.value, "records": [record.model_dump(mode="json") for record in records]},
            summary=f"Found {len(records)} global memory record(s)",
        )


class MemoryWriteTool(ToolExecutor):
    name = "mcp.memory.n--write"
    description = "Write session or private memory through the mediated memory interface"
    input_schema = {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["session", "global", "private"]},
            "session_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["note", "fact", "summary", "lesson"]},
            "source": {"type": "string"},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "task_id": {"type": "string"},
            "approval_id": {"type": "string"},
            "artifact_id": {"type": "string"},
            "linked_event_id": {"type": "string"},
            "promotion_id": {"type": "string"},
        },
        "required": ["scope", "agent_id", "content"],
    }

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        private_memory_store: AgentPrivateMemoryStore | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._private_memory_store = private_memory_store

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        scope = _parse_scope(arguments.get("scope"), allow_private=True)
        if scope is None:
            return _missing_or_invalid("scope")

        execution_context = _parse_execution_context(arguments)

        agent_id = execution_context.get("agent_id") or _parse_required_string(arguments, "agent_id")
        if agent_id is None:
            return _missing_or_invalid("agent_id")

        content = _parse_required_string(arguments, "content")
        if content is None:
            return _missing_or_invalid("content")

        tags = _parse_tags(arguments.get("tags"))

        if scope == "private":
            if self._private_memory_store is None:
                return ToolResult(
                    success=False,
                    error="private memory runtime wiring is deferred until Phase 8",
                )
            record = PrivateMemoryRecord(
                id=generate_prefixed_id("pmr"),
                owner_agent_id=agent_id,
                content=content,
                tags=tuple(tags or []),
            )
            await self._private_memory_store.write(agent_id=agent_id, record=record)
            return ToolResult(
                success=True,
                output={"scope": "private", "record": asdict(record)},
                summary="Wrote private memory record",
            )

        if scope == "global":
            return ToolResult(
                success=False,
                error="global memory must be created only through promotion",
                summary="Direct global memory writes are rejected",
            )

        session_id = execution_context.get("session_id") or _parse_required_string(arguments, "session_id")
        if session_id is None:
            return _missing_or_invalid("session_id")

        try:
            kind = _parse_kind(arguments.get("kind"))
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        session_record = await self._memory_service.write_record(
            scope=MemoryScope.SESSION,
            session_id=session_id,
            agent_id=agent_id,
            kind=kind,
            source=_parse_optional_string(arguments.get("source")) or "tool:memory.write",
            content=content,
            tags=tags,
            task_id=_parse_optional_string(arguments.get("task_id")),
            approval_id=_parse_optional_string(arguments.get("approval_id")),
            artifact_id=_parse_optional_string(arguments.get("artifact_id")),
            linked_event_id=_parse_optional_string(arguments.get("linked_event_id")),
            promotion_id=_parse_optional_string(arguments.get("promotion_id")),
        )
        return ToolResult(
            success=True,
            output={
                "scope": MemoryScope.SESSION.value,
                "record": session_record.model_dump(mode="json"),
            },
            summary="Wrote session memory record",
        )


class MemoryPromoteTool(ToolExecutor):
    name = "mcp.memory.n--promote"
    description = "Promote session memory into global memory through the mediated memory interface"
    input_schema = {
        "type": "object",
        "properties": {
            "record_id": {"type": "string"},
            "session_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "autonomy_level": {"type": "string", "enum": ["supervised", "semi_autonomous", "autonomous"]},
        },
        "required": ["record_id", "session_id", "agent_id", "autonomy_level"],
    }

    def __init__(self, *, memory_service: MemoryService) -> None:
        self._memory_service = memory_service

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        record_id = _parse_required_string(arguments, "record_id")
        if record_id is None:
            return _missing_or_invalid("record_id")

        execution_context = _parse_execution_context(arguments)

        session_id = execution_context.get("session_id") or _parse_required_string(arguments, "session_id")
        if session_id is None:
            return _missing_or_invalid("session_id")

        agent_id = execution_context.get("agent_id") or _parse_required_string(arguments, "agent_id")
        if agent_id is None:
            return _missing_or_invalid("agent_id")

        autonomy_level = _parse_autonomy_level(arguments.get("autonomy_level"))
        if autonomy_level is None:
            return _missing_or_invalid("autonomy_level")

        promotion = await self._memory_service.promote_record(
            record_id=record_id,
            session_id=session_id,
            agent_id=agent_id,
            autonomy_level=autonomy_level,
        )
        return ToolResult(
            success=True,
            output={"promotion": promotion.model_dump(mode="json")},
            summary=f"Promotion {promotion.status.value}",
        )


def _parse_scope(value: Any, *, allow_private: bool = True) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized == MemoryScope.SESSION.value:
        return MemoryScope.SESSION.value
    if normalized == MemoryScope.GLOBAL.value:
        return MemoryScope.GLOBAL.value
    if allow_private and normalized == "private":
        return "private"
    return None


def _parse_kind(value: Any) -> MemoryRecordKind:
    if value is None:
        return MemoryRecordKind.NOTE
    if not isinstance(value, str):
        raise ValueError(f"Invalid kind value: {value}")
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Invalid kind value: ")
    try:
        return MemoryRecordKind(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid kind value: {value}") from exc


def _parse_autonomy_level(value: Any) -> AutonomyLevel | None:
    if not isinstance(value, str):
        return None
    try:
        return AutonomyLevel(value.strip().lower())
    except ValueError:
        return None


def _parse_required_string(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _parse_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _parse_tags(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    tag_values = cast(list[Any], value)
    tags = [str(item).strip() for item in tag_values if str(item).strip()]
    return tags or None


def _parse_limit(value: Any) -> int | None:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    return limit


def _parse_execution_context(arguments: dict[str, Any]) -> dict[str, str]:
    value = arguments.get("_execution_context")
    if not isinstance(value, dict):
        return {}

    raw_context = cast(dict[str, Any], value)
    context: dict[str, str] = {}
    session_id = raw_context.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        context["session_id"] = session_id.strip()
    agent_id = raw_context.get("agent_id")
    if isinstance(agent_id, str) and agent_id.strip():
        context["agent_id"] = agent_id.strip()
    return context


def _missing_or_invalid(argument_name: str) -> ToolResult:
    return ToolResult(success=False, error=f"Missing or invalid argument: {argument_name}")

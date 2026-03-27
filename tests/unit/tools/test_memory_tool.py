from __future__ import annotations

from typing import Any, cast

import pytest

from breqy.domain.enums import AutonomyLevel, MemoryPromotionStatus, MemoryRecordKind, MemoryScope
from breqy.domain.models import MemoryPromotion, MemoryRecord
from breqy.memory.contracts import PrivateMemoryRecord
from breqy.tools.memory import MemoryPromoteTool, MemorySearchTool, MemoryWriteTool


class RecordingMemoryService:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, Any]] = []
        self.write_calls: list[dict[str, Any]] = []
        self.promote_calls: list[dict[str, Any]] = []
        self.search_result = [
            MemoryRecord(
                id="mem_session",
                scope=MemoryScope.SESSION,
                session_id="ses_123",
                agent_id="agt_123",
                kind=MemoryRecordKind.NOTE,
                source="tool:memory.write",
                content="Remember the approved deployment plan.",
                tags=["deployment"],
            )
        ]
        self.write_result = MemoryRecord(
            id="mem_written",
            scope=MemoryScope.SESSION,
            session_id="ses_123",
            agent_id="agt_123",
            kind=MemoryRecordKind.FACT,
            source="tool:memory.write",
            content="The workspace is under /srv/breqy.",
            tags=["workspace"],
        )
        self.promote_result = MemoryPromotion(
            id="mpr_123",
            source_record_id="mem_written",
            target_record_id="mem_global",
            source_session_id="ses_123",
            proposing_agent_id="agt_123",
            status=MemoryPromotionStatus.APPROVED,
        )

    async def search_records(self, **kwargs: Any) -> list[MemoryRecord]:
        self.search_calls.append(kwargs)
        return self.search_result

    async def write_record(self, **kwargs: Any) -> MemoryRecord:
        self.write_calls.append(kwargs)
        return self.write_result

    async def promote_record(self, **kwargs: Any) -> MemoryPromotion:
        self.promote_calls.append(kwargs)
        return self.promote_result


class RecordingPrivateMemoryStore:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, Any]] = []
        self.write_calls: list[dict[str, Any]] = []
        self.search_result = [
            PrivateMemoryRecord(
                id="pmr_123",
                owner_agent_id="agt_123",
                content="Private note for the current agent.",
                tags=("private",),
            )
        ]

    async def search(self, **kwargs: Any) -> list[PrivateMemoryRecord]:
        self.search_calls.append(kwargs)
        return self.search_result

    async def write(self, **kwargs: Any) -> str:
        self.write_calls.append(kwargs)
        record = cast(PrivateMemoryRecord, kwargs["record"])
        return record.id


def build_tools() -> tuple[
    MemorySearchTool,
    MemoryWriteTool,
    MemoryPromoteTool,
    RecordingMemoryService,
    RecordingPrivateMemoryStore,
]:
    memory_service = RecordingMemoryService()
    private_store = RecordingPrivateMemoryStore()
    return (
        MemorySearchTool(memory_service=cast(Any, memory_service), private_memory_store=cast(Any, private_store)),
        MemoryWriteTool(memory_service=cast(Any, memory_service), private_memory_store=cast(Any, private_store)),
        MemoryPromoteTool(memory_service=cast(Any, memory_service)),
        memory_service,
        private_store,
    )


@pytest.mark.asyncio
async def test_memory_tools_expose_stable_mcp_style_names() -> None:
    search_tool, write_tool, promote_tool, _, _ = build_tools()

    assert search_tool.name == "mcp.memory.n--search"
    assert write_tool.name == "mcp.memory.n--write"
    assert promote_tool.name == "mcp.memory.n--promote"


@pytest.mark.asyncio
async def test_memory_search_tool_delegates_session_scope_to_memory_service() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    result = await search_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "query": "deployment",
            "tags": ["deployment"],
            "limit": 5,
        }
    )

    assert result.success is True
    assert result.output["scope"] == "session"
    assert result.output["records"][0]["id"] == "mem_session"
    assert memory_service.search_calls == [
        {
            "scope": MemoryScope.SESSION,
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "query": "deployment",
            "tags": ["deployment"],
            "task_id": None,
            "approval_id": None,
            "artifact_id": None,
            "linked_event_id": None,
            "promotion_id": None,
            "limit": 5,
        }
    ]
    assert private_store.search_calls == []


@pytest.mark.asyncio
async def test_memory_search_tool_routes_private_scope_to_private_store() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    result = await search_tool.execute(
        {
            "scope": "private",
            "agent_id": "agt_123",
            "query": "private note",
            "limit": 3,
        }
    )

    assert result.success is True
    assert result.output["scope"] == "private"
    assert result.output["records"][0]["owner_agent_id"] == "agt_123"
    assert memory_service.search_calls == []
    assert private_store.search_calls == [
        {
            "agent_id": "agt_123",
            "query": "private note",
            "limit": 3,
        }
    ]


@pytest.mark.asyncio
async def test_memory_write_tool_rejects_direct_global_writes() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    result = await write_tool.execute(
        {
            "scope": "global",
            "agent_id": "agt_123",
            "content": "Do not allow direct global writes.",
        }
    )

    assert result.success is False
    assert result.error == "global memory must be created only through promotion"
    assert memory_service.write_calls == []
    assert private_store.write_calls == []


@pytest.mark.asyncio
async def test_memory_write_tool_routes_private_scope_to_private_store() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    result = await write_tool.execute(
        {
            "scope": "private",
            "agent_id": "agt_123",
            "content": "Private note for later.",
            "tags": ["private", "note"],
        }
    )

    assert result.success is True
    assert result.output["scope"] == "private"
    assert result.output["record"]["owner_agent_id"] == "agt_123"
    assert result.output["record"]["content"] == "Private note for later."
    assert memory_service.write_calls == []
    assert len(private_store.write_calls) == 1
    assert private_store.write_calls[0]["agent_id"] == "agt_123"
    record = cast(PrivateMemoryRecord, private_store.write_calls[0]["record"])
    assert record.owner_agent_id == "agt_123"
    assert record.content == "Private note for later."
    assert record.tags == ("private", "note")


@pytest.mark.asyncio
async def test_memory_promote_tool_delegates_to_memory_service() -> None:
    _, _, promote_tool, memory_service, _ = build_tools()

    result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "autonomy_level": "autonomous",
        }
    )

    assert result.success is True
    assert result.output["promotion"]["id"] == "mpr_123"
    assert result.output["promotion"]["status"] == MemoryPromotionStatus.APPROVED.value
    assert memory_service.promote_calls == [
        {
            "record_id": "mem_written",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "autonomy_level": AutonomyLevel.AUTONOMOUS,
        }
    ]


@pytest.mark.asyncio
async def test_memory_tools_expose_input_schema_metadata() -> None:
    search_tool, write_tool, promote_tool, _, _ = build_tools()

    assert search_tool.input_schema["type"] == "object"
    assert search_tool.input_schema["properties"]["scope"]["enum"] == ["session", "global", "private"]
    assert write_tool.input_schema["properties"]["scope"]["enum"] == ["session", "global", "private"]
    assert promote_tool.input_schema["required"] == ["record_id", "session_id", "agent_id", "autonomy_level"]


@pytest.mark.asyncio
async def test_memory_search_tool_rejects_non_positive_limit() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    result = await search_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "limit": 0,
        }
    )

    assert result.success is False
    assert result.error == "Invalid limit value: 0"
    assert memory_service.search_calls == []
    assert private_store.search_calls == []


@pytest.mark.asyncio
async def test_memory_write_tool_rejects_invalid_kind() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "content": "Bad kind should not be downgraded.",
            "kind": "mystery",
        }
    )

    assert result.success is False
    assert result.error == "Invalid kind value: mystery"
    assert memory_service.write_calls == []
    assert private_store.write_calls == []


@pytest.mark.asyncio
async def test_memory_search_tool_requires_session_id_for_session_scope() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    result = await search_tool.execute(
        {
            "scope": "session",
            "agent_id": "agt_123",
        }
    )

    assert result.success is False
    assert result.error == "Missing or invalid argument: session_id"
    assert memory_service.search_calls == []
    assert private_store.search_calls == []


@pytest.mark.asyncio
async def test_memory_search_tool_requires_agent_id_without_execution_context() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    result = await search_tool.execute(
        {
            "scope": "global",
        }
    )

    assert result.success is False
    assert result.error == "Missing or invalid argument: agent_id"
    assert memory_service.search_calls == []
    assert private_store.search_calls == []


@pytest.mark.asyncio
async def test_memory_write_tool_requires_agent_id() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    result = await write_tool.execute(
        {
            "scope": "private",
            "content": "Missing agent should fail.",
        }
    )

    assert result.success is False
    assert result.error == "Missing or invalid argument: agent_id"
    assert memory_service.write_calls == []
    assert private_store.write_calls == []


@pytest.mark.asyncio
async def test_memory_promote_tool_requires_valid_autonomy_level() -> None:
    _, _, promote_tool, memory_service, _ = build_tools()

    result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "autonomy_level": "wild",
        }
    )

    assert result.success is False
    assert result.error == "Missing or invalid argument: autonomy_level"
    assert memory_service.promote_calls == []


@pytest.mark.asyncio
async def test_memory_search_tool_uses_trusted_execution_context_for_session_scope() -> None:
    search_tool, _, _, memory_service, _ = build_tools()

    result = await search_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_spoofed",
            "agent_id": "agt_spoofed",
            "query": "deployment",
            "_execution_context": {"session_id": "ses_trusted", "agent_id": "agt_trusted"},
        }
    )

    assert result.success is True
    assert memory_service.search_calls == [
        {
            "scope": MemoryScope.SESSION,
            "session_id": "ses_trusted",
            "agent_id": "agt_trusted",
            "query": "deployment",
            "tags": None,
            "task_id": None,
            "approval_id": None,
            "artifact_id": None,
            "linked_event_id": None,
            "promotion_id": None,
            "limit": 10,
        }
    ]


@pytest.mark.asyncio
async def test_memory_search_tool_rejects_private_scope_without_runtime_store() -> None:
    search_tool = MemorySearchTool(memory_service=cast(Any, RecordingMemoryService()))

    result = await search_tool.execute(
        {
            "scope": "private",
            "agent_id": "agt_123",
        }
    )

    assert result.success is False
    assert result.error == "private memory runtime wiring is deferred until Phase 8"


@pytest.mark.asyncio
async def test_memory_search_tool_rejects_invalid_scope_and_limit_types() -> None:
    search_tool, _, _, memory_service, private_store = build_tools()

    invalid_scope_result = await search_tool.execute(
        {
            "scope": 123,
            "agent_id": "agt_123",
        }
    )
    invalid_limit_result = await search_tool.execute(
        {
            "scope": "global",
            "agent_id": "agt_123",
            "limit": "ten",
        }
    )

    assert invalid_scope_result.success is False
    assert invalid_scope_result.error == "Missing or invalid argument: scope"
    assert invalid_limit_result.success is False
    assert invalid_limit_result.error == "Invalid limit value: ten"
    assert memory_service.search_calls == []
    assert private_store.search_calls == []


@pytest.mark.asyncio
async def test_memory_write_tool_uses_trusted_execution_context_for_session_scope() -> None:
    _, write_tool, _, memory_service, _ = build_tools()

    result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_spoofed",
            "agent_id": "agt_spoofed",
            "content": "Trusted context should win.",
            "_execution_context": {"session_id": "ses_trusted", "agent_id": "agt_trusted"},
        }
    )

    assert result.success is True
    assert memory_service.write_calls == [
        {
            "scope": MemoryScope.SESSION,
            "session_id": "ses_trusted",
            "agent_id": "agt_trusted",
            "kind": MemoryRecordKind.NOTE,
            "source": "tool:memory.write",
            "content": "Trusted context should win.",
            "tags": None,
            "task_id": None,
            "approval_id": None,
            "artifact_id": None,
            "linked_event_id": None,
            "promotion_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_memory_write_tool_rejects_private_scope_without_runtime_store() -> None:
    write_tool = MemoryWriteTool(memory_service=cast(Any, RecordingMemoryService()))

    result = await write_tool.execute(
        {
            "scope": "private",
            "agent_id": "agt_123",
            "content": "No private runtime store.",
        }
    )

    assert result.success is False
    assert result.error == "private memory runtime wiring is deferred until Phase 8"


@pytest.mark.asyncio
async def test_memory_write_tool_rejects_missing_content_and_invalid_scope_type() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    missing_content_result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
        }
    )
    invalid_scope_result = await write_tool.execute(
        {
            "scope": ["session"],
            "agent_id": "agt_123",
            "content": "bad scope",
        }
    )

    assert missing_content_result.success is False
    assert missing_content_result.error == "Missing or invalid argument: content"
    assert invalid_scope_result.success is False
    assert invalid_scope_result.error == "Missing or invalid argument: scope"
    assert memory_service.write_calls == []
    assert private_store.write_calls == []


@pytest.mark.asyncio
async def test_memory_promote_tool_uses_trusted_execution_context() -> None:
    _, _, promote_tool, memory_service, _ = build_tools()

    result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "session_id": "ses_spoofed",
            "agent_id": "agt_spoofed",
            "autonomy_level": "supervised",
            "_execution_context": {"session_id": "ses_trusted", "agent_id": "agt_trusted"},
        }
    )

    assert result.success is True
    assert memory_service.promote_calls == [
        {
            "record_id": "mem_written",
            "session_id": "ses_trusted",
            "agent_id": "agt_trusted",
            "autonomy_level": AutonomyLevel.SUPERVISED,
        }
    ]


@pytest.mark.asyncio
async def test_memory_promote_tool_requires_record_and_context_fields() -> None:
    _, _, promote_tool, memory_service, _ = build_tools()

    missing_record_result = await promote_tool.execute(
        {
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "autonomy_level": "autonomous",
        }
    )
    missing_session_result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "agent_id": "agt_123",
            "autonomy_level": "autonomous",
        }
    )
    missing_agent_result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "session_id": "ses_123",
            "autonomy_level": "autonomous",
        }
    )

    assert missing_record_result.success is False
    assert missing_record_result.error == "Missing or invalid argument: record_id"
    assert missing_session_result.success is False
    assert missing_session_result.error == "Missing or invalid argument: session_id"
    assert missing_agent_result.success is False
    assert missing_agent_result.error == "Missing or invalid argument: agent_id"
    assert memory_service.promote_calls == []


@pytest.mark.asyncio
async def test_memory_write_tool_requires_session_id_without_execution_context() -> None:
    _, write_tool, _, memory_service, private_store = build_tools()

    result = await write_tool.execute(
        {
            "scope": "session",
            "agent_id": "agt_123",
            "content": "Session id is required.",
        }
    )

    assert result.success is False
    assert result.error == "Missing or invalid argument: session_id"
    assert memory_service.write_calls == []
    assert private_store.write_calls == []


@pytest.mark.asyncio
async def test_memory_tool_parsers_reject_non_string_kind_autonomy_and_optional_fields() -> None:
    _, write_tool, promote_tool, memory_service, _ = build_tools()

    invalid_kind_result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "content": "Bad typed kind.",
            "kind": 7,
            "source": 9,
            "task_id": 10,
            "approval_id": 11,
            "artifact_id": 12,
            "linked_event_id": 13,
            "promotion_id": 14,
            "tags": "not-a-list",
        }
    )
    invalid_autonomy_result = await promote_tool.execute(
        {
            "record_id": "mem_written",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "autonomy_level": 5,
        }
    )

    assert invalid_kind_result.success is False
    assert invalid_kind_result.error == "Invalid kind value: 7"
    assert invalid_autonomy_result.success is False
    assert invalid_autonomy_result.error == "Missing or invalid argument: autonomy_level"
    assert memory_service.write_calls == []
    assert memory_service.promote_calls == []


@pytest.mark.asyncio
async def test_memory_tool_parsers_handle_blank_optional_strings_and_unsupported_scope_value() -> None:
    _, write_tool, _, memory_service, _ = build_tools()

    unsupported_scope_result = await write_tool.execute(
        {
            "scope": "workspace",
            "agent_id": "agt_123",
            "content": "bad scope",
        }
    )
    blank_optional_result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "content": "blank optional fields become None",
            "source": "   ",
            "task_id": "   ",
            "approval_id": "   ",
            "artifact_id": "   ",
            "linked_event_id": "   ",
            "promotion_id": "   ",
        }
    )

    assert unsupported_scope_result.success is False
    assert unsupported_scope_result.error == "Missing or invalid argument: scope"
    assert blank_optional_result.success is True
    assert memory_service.write_calls[-1] == {
        "scope": MemoryScope.SESSION,
        "session_id": "ses_123",
        "agent_id": "agt_123",
        "kind": MemoryRecordKind.NOTE,
        "source": "tool:memory.write",
        "content": "blank optional fields become None",
        "tags": None,
        "task_id": None,
        "approval_id": None,
        "artifact_id": None,
        "linked_event_id": None,
        "promotion_id": None,
    }


@pytest.mark.asyncio
async def test_memory_write_tool_rejects_blank_kind_string() -> None:
    _, write_tool, _, memory_service, _ = build_tools()

    result = await write_tool.execute(
        {
            "scope": "session",
            "session_id": "ses_123",
            "agent_id": "agt_123",
            "content": "Blank kind should fail.",
            "kind": "   ",
        }
    )

    assert result.success is False
    assert result.error == "Invalid kind value: "
    assert memory_service.write_calls == []

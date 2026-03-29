"""Tests for EngineServer tool wiring."""
from __future__ import annotations

from typing import Any, cast

import pytest

from breqy.a2a.envelope import Envelope
from breqy.domain.events import (
    AgentLifecycleEvent,
    AgentWorkRequestedEvent,
    ControlEvent,
    MessageSentEvent,
    PrivateMemoryOperationRequestedEvent,
    TaskUpdatedEvent,
    ToolExecutionRequestedEvent,
)
from breqy.domain.enums import EventType, MemoryScope, MessageRole, TaskStatus, ToolStatus
from breqy.domain.models import Session, SessionContextBundle
from breqy.engine.server import EngineServer
from breqy.memory.service import MemoryService
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.participant_repo import SqliteParticipantRepository
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.storage.sqlite.tool_invocation_repo import SqliteToolInvocationRepository
from breqy.tools.registry import ToolRegistry
from breqy.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_engine_server_composes_tool_service_and_persists_tool_events(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    registry = ToolRegistry()
    registry.register(ShellTool())

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        tool_invocation_repo=invocation_repo,
        tool_registry=registry,
        policy_evaluator=PolicyEvaluator([]),
        filesystem_policy_checker=FilesystemPolicyChecker([]),
        approval_service=ApprovalService(approval_repo),
    )

    await server.start()
    try:
        result = await server.execute_tool(
            session_id=session.id,
            agent_id="agent_breqy",
            tool_name="shell",
            arguments={"command": "printf hello"},
        )
    finally:
        await server.stop()

    assert result.success is True
    assert result.output == {"stdout": "hello", "stderr": "", "return_code": 0}

    invocations = await invocation_repo.list_by_session(session.id)
    assert len(invocations) == 1
    assert invocations[0].tool_name == "shell"
    assert invocations[0].status == ToolStatus.COMPLETED
    assert invocations[0].result == result.output

    events = await event_repo.list_by_session(session.id, limit=10)
    assert [event.event_type for event in events] == [
        EventType.TOOL_INVOCATION_STARTED,
        EventType.TOOL_INVOCATION_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_engine_server_execute_tool_fails_when_tool_service_is_unavailable(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    with pytest.raises(RuntimeError, match="Tool service is not configured"):
        await server.execute_tool(
            session_id="ses_missing",
            agent_id="agent_breqy",
            tool_name="shell",
            arguments={"command": "printf hello"},
        )


@pytest.mark.asyncio
async def test_engine_server_default_tool_registry_registers_memory_tools(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        memory_repo=memory_repo,
        tool_invocation_repo=invocation_repo,
    )

    assert server.tool_service is not None
    assert server.tool_service._registry.get("mcp.memory.n--search") is not None
    assert server.tool_service._registry.get("mcp.memory.n--write") is not None
    assert server.tool_service._registry.get("mcp.memory.n--promote") is not None


@pytest.mark.asyncio
async def test_engine_server_composes_memory_service_with_sqlite_memory_repo(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        memory_repo=memory_repo,
        tool_invocation_repo=invocation_repo,
    )

    assert isinstance(server.memory_service, MemoryService)
    assert isinstance(server.memory_service._repository, SqliteMemoryRepository)


@pytest.mark.asyncio
async def test_engine_server_persists_memory_events_through_engine_event_flow(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        memory_repo=memory_repo,
        tool_invocation_repo=invocation_repo,
    )

    await server.start()
    try:
        result = await server.execute_tool(
            session_id=session.id,
            agent_id="agent_breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "session",
                "session_id": session.id,
                "agent_id": "agent_breqy",
                "kind": "fact",
                "content": "Engine-composed memory writes must emit durable events.",
                "tags": ["engine", "memory"],
            },
        )
    finally:
        await server.stop()

    assert result.success is True
    assert result.output["scope"] == "session"
    assert result.output["record"]["scope"] == MemoryScope.SESSION.value

    events = await event_repo.list_by_session(session.id, limit=10)
    assert [event.event_type for event in events] == [
        EventType.TOOL_INVOCATION_STARTED,
        EventType.MEMORY_RECORD_CREATED,
        EventType.TOOL_INVOCATION_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_engine_server_memory_tools_use_engine_execution_context_over_tool_arguments(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        memory_repo=memory_repo,
        tool_invocation_repo=invocation_repo,
    )

    await server.start()
    try:
        result = await server.execute_tool(
            session_id=session.id,
            agent_id="agent_breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "session",
                "session_id": "ses_spoofed",
                "agent_id": "agent_spoofed",
                "kind": "fact",
                "content": "Canonical memory writes should use engine execution context.",
            },
        )
    finally:
        await server.stop()

    assert result.success is True
    assert result.output["record"]["session_id"] == session.id
    assert result.output["record"]["agent_id"] == "agent_breqy"


@pytest.mark.asyncio
async def test_engine_server_default_runtime_rejects_private_memory_until_phase8_wiring(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    memory_repo = SqliteMemoryRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)

    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        memory_repo=memory_repo,
        tool_invocation_repo=invocation_repo,
    )

    await server.start()
    try:
        result = await server.execute_tool(
            session_id=session.id,
            agent_id="agent_breqy",
            tool_name="mcp.memory.n--write",
            arguments={
                "scope": "private",
                "agent_id": "agent_spoofed",
                "content": "Private runtime wiring is deferred.",
            },
        )
    finally:
        await server.stop()

    assert result.success is False
    assert "phase 8" in result.error.lower()


@pytest.mark.asyncio
async def test_engine_server_handle_envelope_publishes_and_broadcasts(socket_path) -> None:
    class RecordingMessageRepo:
        def __init__(self) -> None:
            self.created: list[object] = []

        async def create(self, message: object) -> None:
            self.created.append(message)

    class RecordingSessionRepo:
        def __init__(self) -> None:
            self.updated: list[str] = []

        async def update_timestamp(self, session_id: str) -> None:
            self.updated.append(session_id)

    message_repo = RecordingMessageRepo()
    session_repo = RecordingSessionRepo()
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, session_repo),
        message_repo=cast(Any, message_repo),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def publish(event: object) -> None:
        published.append(event)

    async def broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = broadcast  # type: ignore[method-assign]

    event = MessageSentEvent(
        session_id="ses_123",
        message_id="msg_123",
        role=MessageRole.ASSISTANT,
        content="hello",
    )
    envelope = Envelope.from_event(event)

    await server._handle_envelope(envelope, client_id="client_1")

    assert published == [event]
    assert broadcasts == [(envelope, "client_1")]
    assert len(message_repo.created) == 1
    assert session_repo.updated == ["ses_123"]


@pytest.mark.asyncio
async def test_engine_server_registers_agent_connection_from_lifecycle_event(socket_path) -> None:
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    async def publish(_: object) -> None:
        return None

    async def broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.event_bus.publish = publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = broadcast  # type: ignore[method-assign]

    event = AgentLifecycleEvent(
        event_type=EventType.AGENT_CONNECTED,
        session_id="ses_123",
        agent_id="agt_breqy",
    )

    await server._handle_envelope(Envelope.from_event(event), client_id="cli_123")

    info = server.agent_registry.get("agt_breqy")
    assert info is not None
    assert info.client_id == "cli_123"


@pytest.mark.asyncio
async def test_engine_server_disconnect_callback_unregisters_agent(socket_path) -> None:
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    server.agent_registry.register("agt_breqy", client_id="cli_123")

    await server._handle_disconnect("cli_123")

    assert server.agent_registry.get("agt_breqy") is None


@pytest.mark.asyncio
async def test_engine_server_routes_user_message_to_primary_agent_with_work_request(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent")
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]
    server.a2a_server.broadcast = cast(Any, lambda envelope, exclude_client="": None)

    event = MessageSentEvent(
        session_id=session.id,
        message_id="msg_user",
        role=MessageRole.USER,
        content="Continue Phase 8.",
    )

    await server._handle_envelope(Envelope.from_event(event), client_id="cli_tui")

    stored_messages = await message_repo.list_by_session(session.id)
    assert [message.content for message in stored_messages] == ["Continue Phase 8."]
    assert len(sent) == 1
    assert sent[0][0] == "cli_agent"
    routed_event = sent[0][1].to_event()
    assert isinstance(routed_event, AgentWorkRequestedEvent)
    assert routed_event.user_message_content == "Continue Phase 8."
    assert routed_event.session_context == SessionContextBundle(messages=stored_messages)


@pytest.mark.asyncio
async def test_engine_server_routes_tool_execution_request_directly_without_persisting_transport_event(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        tool_invocation_repo=invocation_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent")
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]
    request = ToolExecutionRequestedEvent(
        session_id=session.id,
        agent_id="agt_breqy",
        correlation_id="inv_123",
        invocation_id="inv_123",
        tool_name="filesystem",
        arguments={"path": "/tmp/example", "operation": "read"},
    )

    await server._handle_envelope(Envelope.from_event(request), client_id="cli_agent")

    persisted_events = await event_repo.list_by_session(session.id, limit=20)
    assert EventType.TOOL_EXECUTION_REQUESTED not in [event.event_type for event in persisted_events]
    assert sent[0][0] == "cli_agent"
    assert sent[0][1].event_type == EventType.TOOL_EXECUTION_RESULT


@pytest.mark.asyncio
async def test_engine_server_routes_private_memory_request_directly_without_persisting_transport_event(
    db_connection,
    socket_path,
) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent")
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]
    request = PrivateMemoryOperationRequestedEvent(
        session_id=session.id,
        agent_id="agt_breqy",
        correlation_id="inv_private",
        invocation_id="inv_private",
        operation_name="search",
        arguments={"query": "secret"},
    )

    await server._handle_envelope(Envelope.from_event(request), client_id="cli_engine")

    persisted_events = await event_repo.list_by_session(session.id, limit=20)
    assert EventType.PRIVATE_MEMORY_OPERATION_REQUESTED not in [event.event_type for event in persisted_events]
    assert sent[0][0] == "cli_agent"
    assert sent[0][1].event_type == EventType.PRIVATE_MEMORY_OPERATION_REQUESTED


@pytest.mark.asyncio
async def test_engine_server_user_message_returns_early_when_session_missing(socket_path) -> None:
    class MessageRepo:
        async def create(self, message: object) -> None:
            return None

        async def list_by_session(self, session_id: str, limit: int = 100):
            return []

    class SessionRepo:
        async def update_timestamp(self, session_id: str) -> None:
            return None

        async def get(self, session_id: str):
            return None

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, SessionRepo()),
        message_repo=cast(Any, MessageRepo()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    send_calls: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        send_calls.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    async def fake_publish(event: object) -> None:
        return None

    server.event_bus.publish = fake_publish  # type: ignore[method-assign]

    await server._handle_user_message(
        MessageSentEvent(session_id="ses_missing", message_id="msg_1", role=MessageRole.USER, content="hello")
    )

    assert send_calls == []


@pytest.mark.asyncio
async def test_engine_server_user_message_returns_early_when_primary_agent_missing(db_connection, socket_path) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_missing")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    await server._handle_user_message(
        MessageSentEvent(session_id=session.id, message_id="msg_1", role=MessageRole.USER, content="hello")
    )

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_tool_request_returns_early_when_agent_not_registered(db_connection, socket_path) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        tool_invocation_repo=invocation_repo,
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    await server._handle_tool_execution_request(
        ToolExecutionRequestedEvent(
            session_id=session.id,
            agent_id="agt_missing",
            correlation_id="inv_ok",
            invocation_id="inv_ok",
            tool_name="filesystem",
            arguments={"path": "/tmp/example", "operation": "read"},
        )
    )

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_tool_request_success_branch_returns_structured_success(db_connection, socket_path) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    invocation_repo = SqliteToolInvocationRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)
    success_file = socket_path.parent / "success.txt"
    success_file.write_text("hello")

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        tool_invocation_repo=invocation_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent")
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    await server._handle_tool_execution_request(
        ToolExecutionRequestedEvent(
            session_id=session.id,
            agent_id="agt_breqy",
            correlation_id="inv_ok",
            invocation_id="inv_ok",
            tool_name="filesystem",
            arguments={"path": str(success_file), "operation": "read"},
        )
    )

    response = cast(Any, sent[0][1].to_event())
    assert sent[0][0] == "cli_agent"
    assert response.success_payload is not None
    assert response.failure_payload is None


@pytest.mark.asyncio
async def test_engine_server_private_memory_request_returns_early_when_agent_not_registered(socket_path) -> None:
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    await server._route_private_memory_request(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_1",
            agent_id="agt_missing",
            correlation_id="inv_private",
            invocation_id="inv_private",
            operation_name="search",
            arguments={"query": "secret"},
        )
    )

    assert sent == []


# --------------------------------------------------------------------------- #
# Phase 9, Task 9: EngineServer integration wiring tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_engine_server_accepts_participant_repo_and_creates_control_handler(
    db_connection,
    socket_path,
) -> None:
    """EngineServer wires participant_repo into SessionManager and creates ControlHandler + TaskManager."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        participant_repo=participant_repo,
    )

    # ControlHandler and TaskManager are wired
    assert server.control_handler is not None
    assert server.task_manager is not None
    # SessionManager has participant_repo wired
    assert server.session_manager._participants is participant_repo


@pytest.mark.asyncio
async def test_engine_server_routes_control_event_to_control_handler(socket_path) -> None:
    """ControlEvents in _handle_envelope are delegated to ControlHandler."""
    handled_controls: list[object] = []

    class FakeControlHandler:
        async def handle_control(self, event: object) -> None:
            handled_controls.append(event)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    server.control_handler = cast(Any, FakeControlHandler())  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    control_event = ControlEvent(
        session_id="ses_1",
        event_type=EventType.CONTROL_STOP,
    )
    await server._handle_envelope(Envelope.from_event(control_event), client_id="cli_tui")

    assert len(handled_controls) == 1
    assert handled_controls[0].event_type == EventType.CONTROL_STOP


@pytest.mark.asyncio
async def test_engine_server_control_event_is_not_broadcast(socket_path) -> None:
    """ControlEvents should be routed to ControlHandler, NOT broadcast to other clients."""
    broadcasts: list[object] = []

    class FakeControlHandler:
        async def handle_control(self, event: object) -> None:
            pass

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    server.control_handler = cast(Any, FakeControlHandler())  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append(envelope)

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    control_event = ControlEvent(
        session_id="ses_1",
        event_type=EventType.CONTROL_STEER,
        new_direction="focus on tests",
    )
    await server._handle_envelope(Envelope.from_event(control_event), client_id="cli_tui")

    assert broadcasts == []


@pytest.mark.asyncio
async def test_engine_server_agent_connect_creates_participant(
    db_connection,
    socket_path,
) -> None:
    """AGENT_CONNECTED lifecycle event creates a Participant record."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)

    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        participant_repo=participant_repo,
    )

    async def noop_publish(_: object) -> None:
        return None

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    event = AgentLifecycleEvent(
        event_type=EventType.AGENT_CONNECTED,
        session_id=session.id,
        agent_id="agt_breqy",
    )
    await server._handle_envelope(Envelope.from_event(event), client_id="cli_agent")

    # Agent registered in registry with session_id
    info = server.agent_registry.get("agt_breqy")
    assert info is not None
    assert info.session_id == session.id

    # Participant record created
    participants = await participant_repo.get_active_by_session(session.id)
    assert len(participants) == 1
    assert participants[0].agent_id == "agt_breqy"
    assert participants[0].session_id == session.id


@pytest.mark.asyncio
async def test_engine_server_disconnect_marks_participant_left(
    db_connection,
    socket_path,
) -> None:
    """On disconnect, the agent's participant record should have left_at set."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)

    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
        participant_repo=participant_repo,
    )

    # Simulate agent connection: register in registry and create participant
    server.agent_registry.register("agt_breqy", client_id="cli_agent", session_id=session.id)
    await server.session_manager.add_participant(session.id, "agt_breqy")

    # Verify participant is active
    active = await participant_repo.get_active_by_session(session.id)
    assert len(active) == 1

    # Disconnect
    await server._handle_disconnect("cli_agent")

    # Agent unregistered
    assert server.agent_registry.get("agt_breqy") is None

    # Participant marked as left
    active_after = await participant_repo.get_active_by_session(session.id)
    assert len(active_after) == 0
    all_participants = await participant_repo.list_by_session(session.id)
    assert len(all_participants) == 1
    assert all_participants[0].left_at is not None


@pytest.mark.asyncio
async def test_engine_server_routes_task_updated_event_and_persists(
    db_connection,
    socket_path,
) -> None:
    """TaskUpdatedEvent envelopes are published and broadcast normally."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_publish(event: object) -> None:
        published.append(event)

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = recording_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    task_event = TaskUpdatedEvent(
        session_id=session.id,
        task_id="tsk_123",
        title="Write tests",
        status=TaskStatus.RUNNING,
        event_type=EventType.TASK_UPDATED,
    )
    await server._handle_envelope(Envelope.from_event(task_event), client_id="cli_agent")

    # TaskUpdatedEvent is published and broadcast
    assert len(published) == 1
    assert published[0].event_type == EventType.TASK_UPDATED
    assert len(broadcasts) == 1


@pytest.mark.asyncio
async def test_engine_server_without_participant_repo_still_works(socket_path) -> None:
    """When no participant_repo is provided, EngineServer still functions (backward compat)."""
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )

    # No control_handler when participant_repo is absent
    assert server.control_handler is None
    # TaskManager is always created
    assert server.task_manager is not None


@pytest.mark.asyncio
async def test_engine_server_control_event_falls_through_when_no_control_handler(socket_path) -> None:
    """Without participant_repo, control events fall through to generic publish+broadcast."""
    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )

    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_publish(event: object) -> None:
        published.append(event)

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = recording_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    control_event = ControlEvent(
        session_id="ses_1",
        event_type=EventType.CONTROL_STOP,
    )
    await server._handle_envelope(Envelope.from_event(control_event), client_id="cli_tui")

    # Falls through to generic publish + broadcast
    assert len(published) == 1
    assert len(broadcasts) == 1


# --------------------------------------------------------------------------- #
# Session creation via SessionCreateRequestedEvent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_engine_server_handles_session_create_requested(
    db_connection,
    socket_path,
) -> None:
    """SessionCreateRequestedEvent creates a session and broadcasts SessionCreatedEvent."""
    from breqy.domain.events import SessionCreateRequestedEvent, SessionCreatedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    request = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="agt_default",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # A session should have been created
    sessions = await session_repo.list_active()
    assert len(sessions) == 1
    assert sessions[0].primary_agent_id == "agt_default"

    # A SessionCreatedEvent should have been broadcast
    assert len(broadcasts) == 1
    response_event = broadcasts[0][0].to_event()
    assert isinstance(response_event, SessionCreatedEvent)
    assert response_event.session_id == sessions[0].id
    assert response_event.primary_agent_id == "agt_default"
    # Exclude the requesting client
    assert broadcasts[0][1] == ""


@pytest.mark.asyncio
async def test_engine_server_session_create_requested_is_not_generic_broadcast(
    db_connection,
    socket_path,
) -> None:
    """SessionCreateRequestedEvent should NOT fall through to generic publish+broadcast."""
    from breqy.domain.events import SessionCreateRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_publish(event: object) -> None:
        published.append(event)

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = recording_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    request = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="agt_default",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # The request event itself should NOT be published to the event bus
    assert not any(
        hasattr(e, "event_type") and getattr(e, "event_type") == EventType.SESSION_CREATE_REQUESTED
        for e in published
    )

    # Only the SessionCreatedEvent broadcast should exist
    assert len(broadcasts) == 1
    assert broadcasts[0][0].event_type == EventType.SESSION_CREATED


@pytest.mark.asyncio
async def test_engine_server_spawns_agent_on_session_create(
    db_connection,
    socket_path,
) -> None:
    """SessionCreateRequestedEvent spawns an agent for the new session."""
    from breqy.domain.events import SessionCreateRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    async def noop_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        pass

    async def noop_publish(_: object) -> None:
        pass

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    # Track spawn calls
    spawned: list[tuple[str, str]] = []

    def tracking_spawn(agent_dir: str, *, session_id: str = "") -> int:
        spawned.append((agent_dir, session_id))
        return 99999

    server.agent_spawner.spawn = tracking_spawn  # type: ignore[method-assign]

    request = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="default",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # An agent should have been spawned for the new session
    assert len(spawned) == 1
    assert spawned[0][0] == "agents/breqy"  # "default" maps to agents/breqy
    # session_id should be the newly created session's ID
    sessions = await session_repo.list_active()
    assert spawned[0][1] == sessions[0].id


@pytest.mark.asyncio
async def test_engine_server_session_create_normalizes_default_agent_id(
    db_connection,
    socket_path,
) -> None:
    """Session created with requested_agent_id='default' stores 'breqy' as primary_agent_id.

    This ensures the session's primary_agent_id matches the agent's registered ID
    so that message routing (agent_registry.get(session.primary_agent_id)) succeeds.
    """
    from breqy.domain.events import SessionCreateRequestedEvent, SessionCreatedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    def noop_spawn(agent_dir: str, *, session_id: str = "") -> int:
        return 99999

    server.agent_spawner.spawn = noop_spawn  # type: ignore[method-assign]

    request = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="default",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # The session should store "breqy" not "default"
    sessions = await session_repo.list_active()
    assert len(sessions) == 1
    assert sessions[0].primary_agent_id == "breqy"

    # The broadcast should also reflect the resolved agent_id
    response_event = broadcasts[0][0].to_event()
    assert isinstance(response_event, SessionCreatedEvent)
    assert response_event.primary_agent_id == "breqy"


@pytest.mark.asyncio
async def test_engine_server_session_create_preserves_explicit_agent_id(
    db_connection,
    socket_path,
) -> None:
    """Session created with an explicit agent_id (not 'default') preserves it."""
    from breqy.domain.events import SessionCreateRequestedEvent, SessionCreatedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )

    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    def noop_spawn(agent_dir: str, *, session_id: str = "") -> int:
        return 99999

    server.agent_spawner.spawn = noop_spawn  # type: ignore[method-assign]

    request = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="custom_agent",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    sessions = await session_repo.list_active()
    assert len(sessions) == 1
    assert sessions[0].primary_agent_id == "custom_agent"


# --------------------------------------------------------------------------- #
# Observability: Task 6 — DEBUG trace calls in engine server
# --------------------------------------------------------------------------- #


def test_handle_envelope_logs_debug() -> None:
    """_handle_envelope should contain logger.debug calls for envelope tracing."""
    import inspect
    from breqy.engine import server as server_module

    source = inspect.getsource(server_module.EngineServer._handle_envelope)
    assert "logger.debug" in source, (
        "_handle_envelope must have logger.debug calls for envelope tracing"
    )


def test_handle_user_message_logs_debug() -> None:
    """_handle_user_message should contain logger.debug calls for persist+dispatch tracing."""
    import inspect
    from breqy.engine import server as server_module

    source = inspect.getsource(server_module.EngineServer._handle_user_message)
    assert "logger.debug" in source, (
        "_handle_user_message must have logger.debug calls for message persist/dispatch tracing"
    )


def test_handle_runtime_message_logs_debug() -> None:
    """_handle_runtime_message should contain logger.debug for runtime message tracing."""
    import inspect
    from breqy.engine import server as server_module

    source = inspect.getsource(server_module.EngineServer._handle_runtime_message)
    assert "logger.debug" in source, (
        "_handle_runtime_message must have logger.debug calls for runtime message tracing"
    )


# --------------------------------------------------------------------------- #
# Phase 4 (M2): Engine routing for model events
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_engine_server_routes_model_list_request_to_primary_agent(
    db_connection,
    socket_path,
) -> None:
    """ModelListRequestedEvent from TUI is forwarded to the session's primary agent via send_to."""
    from breqy.domain.events import ModelListRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent", session_id=session.id)
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    # Suppress default broadcast to verify the event is NOT broadcast
    broadcasts: list[object] = []

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append(envelope)

    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelListRequestedEvent(session_id=session.id)
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # Forwarded to the primary agent via send_to
    assert len(sent) == 1
    assert sent[0][0] == "cli_agent"
    assert sent[0][1].event_type == EventType.MODEL_LIST_REQUESTED

    # NOT broadcast to all clients
    assert broadcasts == []


@pytest.mark.asyncio
async def test_engine_server_routes_model_switch_request_to_primary_agent(
    db_connection,
    socket_path,
) -> None:
    """ModelSwitchRequestedEvent from TUI is forwarded to the session's primary agent via send_to."""
    from breqy.domain.events import ModelSwitchRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_breqy")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    server.agent_registry.register("agt_breqy", client_id="cli_agent", session_id=session.id)
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    broadcasts: list[object] = []

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append(envelope)

    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelSwitchRequestedEvent(
        session_id=session.id,
        provider_id="copilot",
        model_id="gpt-4o",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    # Forwarded to the primary agent via send_to
    assert len(sent) == 1
    assert sent[0][0] == "cli_agent"
    routed_event = sent[0][1].to_event()
    assert isinstance(routed_event, ModelSwitchRequestedEvent)
    assert routed_event.provider_id == "copilot"
    assert routed_event.model_id == "gpt-4o"

    # NOT broadcast to all clients
    assert broadcasts == []


@pytest.mark.asyncio
async def test_engine_server_model_list_request_returns_early_when_session_missing(
    socket_path,
) -> None:
    """ModelListRequestedEvent with unknown session_id silently returns without send_to."""
    from breqy.domain.events import ModelListRequestedEvent

    class FakeSessionRepo:
        async def get(self, session_id: str):
            return None

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, FakeSessionRepo()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelListRequestedEvent(session_id="ses_nonexistent")
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_model_switch_request_returns_early_when_session_missing(
    socket_path,
) -> None:
    """ModelSwitchRequestedEvent with unknown session_id silently returns without send_to."""
    from breqy.domain.events import ModelSwitchRequestedEvent

    class FakeSessionRepo:
        async def get(self, session_id: str):
            return None

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, FakeSessionRepo()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelSwitchRequestedEvent(
        session_id="ses_nonexistent",
        provider_id="copilot",
        model_id="gpt-4o",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_model_list_request_returns_early_when_agent_not_registered(
    db_connection,
    socket_path,
) -> None:
    """ModelListRequestedEvent returns early when primary agent is not in the registry."""
    from breqy.domain.events import ModelListRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_missing")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    # Do NOT register "agt_missing" in the registry
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelListRequestedEvent(session_id=session.id)
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_model_switch_request_returns_early_when_agent_not_registered(
    db_connection,
    socket_path,
) -> None:
    """ModelSwitchRequestedEvent returns early when primary agent is not in the registry."""
    from breqy.domain.events import ModelSwitchRequestedEvent

    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    event_repo = SqliteEventRepository(db_connection)
    task_repo = SqliteTaskRepository(db_connection)
    approval_repo = SqliteApprovalRepository(db_connection)
    session = Session(primary_agent_id="agt_missing")
    await session_repo.create(session)

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=session_repo,
        message_repo=message_repo,
        event_repo=event_repo,
        task_repo=task_repo,
        approval_repo=approval_repo,
    )
    sent: list[tuple[str, Envelope]] = []

    async def fake_send_to(client_id: str, envelope: Envelope) -> None:
        sent.append((client_id, envelope))

    server.a2a_server.send_to = fake_send_to  # type: ignore[method-assign]

    async def noop_broadcast(_: Envelope, exclude_client: str = "") -> None:
        return None

    server.a2a_server.broadcast = noop_broadcast  # type: ignore[method-assign]

    async def noop_publish(_: object) -> None:
        return None

    server.event_bus.publish = noop_publish  # type: ignore[method-assign]

    request = ModelSwitchRequestedEvent(
        session_id=session.id,
        provider_id="copilot",
        model_id="gpt-4o",
    )
    await server._handle_envelope(Envelope.from_event(request), client_id="cli_tui")

    assert sent == []


@pytest.mark.asyncio
async def test_engine_server_model_info_event_uses_default_broadcast(
    socket_path,
) -> None:
    """ModelInfoEvent (agent → TUI) falls through to default publish+broadcast."""
    from breqy.domain.events import ModelInfoEvent

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_publish(event: object) -> None:
        published.append(event)

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = recording_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    event = ModelInfoEvent(
        session_id="ses_123",
        agent_id="agt_breqy",
        provider_id="copilot",
        model_id="gpt-4o",
    )
    await server._handle_envelope(Envelope.from_event(event), client_id="cli_agent")

    assert len(published) == 1
    assert published[0].event_type == EventType.MODEL_INFO
    assert len(broadcasts) == 1
    assert broadcasts[0][1] == "cli_agent"


@pytest.mark.asyncio
async def test_engine_server_model_list_response_uses_default_broadcast(
    socket_path,
) -> None:
    """ModelListResponseEvent (agent → TUI) falls through to default publish+broadcast."""
    from breqy.domain.events import ModelListResponseEvent

    server = EngineServer(
        socket_path=str(socket_path),
        session_repo=cast(Any, object()),
        message_repo=cast(Any, object()),
        event_repo=cast(Any, object()),
        task_repo=cast(Any, object()),
        approval_repo=cast(Any, object()),
    )
    published: list[object] = []
    broadcasts: list[tuple[Envelope, str]] = []

    async def recording_publish(event: object) -> None:
        published.append(event)

    async def recording_broadcast(envelope: Envelope, exclude_client: str = "") -> None:
        broadcasts.append((envelope, exclude_client))

    server.event_bus.publish = recording_publish  # type: ignore[method-assign]
    server.a2a_server.broadcast = recording_broadcast  # type: ignore[method-assign]

    event = ModelListResponseEvent(
        session_id="ses_123",
        agent_id="agt_breqy",
        models=[],
        current_provider="copilot",
        current_model="gpt-4o",
    )
    await server._handle_envelope(Envelope.from_event(event), client_id="cli_agent")

    assert len(published) == 1
    assert published[0].event_type == EventType.MODEL_LIST_RESPONSE
    assert len(broadcasts) == 1
    assert broadcasts[0][1] == "cli_agent"

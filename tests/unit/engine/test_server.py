"""Tests for EngineServer tool wiring."""
from __future__ import annotations

import pytest

from breqy.domain.enums import EventType, ToolStatus
from breqy.domain.models import Session
from breqy.engine.server import EngineServer
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
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

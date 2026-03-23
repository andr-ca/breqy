import pytest

from breqy.domain.enums import ToolStatus
from breqy.domain.models import Session, ToolInvocation
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.tool_invocation_repo import SqliteToolInvocationRepository


@pytest.mark.asyncio
async def test_create_and_get_tool_invocation(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(
        session_id=session.id,
        agent_id="breqy",
        tool_name="shell",
        arguments={"command": "echo hello"},
    )

    await repo.create(invocation)
    loaded = await repo.get(invocation.id)

    assert loaded is not None
    assert loaded.tool_name == "shell"
    assert loaded.arguments["command"] == "echo hello"


@pytest.mark.asyncio
async def test_update_status_and_result(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    await repo.create(invocation)

    await repo.update_result(
        invocation.id,
        status=ToolStatus.COMPLETED,
        result={"stdout": "ok", "return_code": 0},
        error="",
        summary="Command exited with code 0",
    )

    loaded = await repo.get(invocation.id)
    assert loaded is not None
    assert loaded.status == ToolStatus.COMPLETED
    assert loaded.result == {"stdout": "ok", "return_code": 0}
    assert loaded.summary == "Command exited with code 0"
    assert loaded.completed_at is not None


@pytest.mark.asyncio
async def test_update_result_keeps_completed_at_none_for_non_final_status(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    await repo.create(invocation)

    await repo.update_result(
        invocation.id,
        status=ToolStatus.RUNNING,
        result={"stdout": "still working"},
        error="",
        summary="Command is still running",
    )

    loaded = await repo.get(invocation.id)

    assert loaded is not None
    assert loaded.status == ToolStatus.RUNNING
    assert loaded.completed_at is None


@pytest.mark.asyncio
async def test_update_result_persists_approval_id_for_final_status(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    await repo.create(invocation)

    await repo.update_result(
        invocation.id,
        status=ToolStatus.FAILED,
        result={"stderr": "permission denied"},
        error="permission denied",
        summary="Command failed",
        approval_id="apr_123",
    )

    loaded = await repo.get(invocation.id)

    assert loaded is not None
    assert loaded.status == ToolStatus.FAILED
    assert loaded.approval_id == "apr_123"
    assert loaded.completed_at is not None


@pytest.mark.asyncio
async def test_list_by_session_returns_newest_first(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    first = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    second = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="filesystem")
    await repo.create(first)
    await repo.create(second)

    invocations = await repo.list_by_session(session.id)

    assert [item.id for item in invocations] == [second.id, first.id]

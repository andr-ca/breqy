"""Tests for SQLite event repository (append-only)."""

import pytest

from breqy.domain.events import MessageSentEvent, ToolInvocationStartedEvent
from breqy.domain.models import Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository


@pytest.mark.asyncio
async def test_append_and_list_events(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    e1 = MessageSentEvent(
        session_id=session.id, message_id="msg_1", role="user", content="Hello"
    )
    e2 = ToolInvocationStartedEvent(
        session_id=session.id,
        agent_id="agent_breqy",
        invocation_id="inv_1",
        tool_name="shell",
        arguments={"command": "ls"},
        summary="List files",
    )
    await event_repo.append(e1)
    await event_repo.append(e2)

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 2
    assert events[0].event_type.value == "message.sent"
    assert events[1].event_type.value == "tool.invocation.started"


@pytest.mark.asyncio
async def test_list_events_after_id(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    events_in = []
    for i in range(5):
        e = MessageSentEvent(
            session_id=session.id,
            message_id=f"msg_{i}",
            role="user",
            content=f"msg {i}",
        )
        await event_repo.append(e)
        events_in.append(e)

    # Events after the 2nd one → should return 3
    events = await event_repo.list_by_session(
        session.id, after_event_id=events_in[1].event_id
    )
    assert len(events) == 3


@pytest.mark.asyncio
async def test_event_roundtrip(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    e = MessageSentEvent(
        session_id=session.id, message_id="msg_x", role="user", content="Round trip"
    )
    await event_repo.append(e)

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 1
    assert events[0].event_id == e.event_id
    assert events[0].session_id == session.id

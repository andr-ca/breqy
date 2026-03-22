"""Tests for the centralized EventWriter (STR-05).

The EventWriter accepts events from multiple async producers and writes
them sequentially without data races. Agents must not write directly to DB.
"""

import asyncio

import pytest

from breqy.domain.events import MessageSentEvent
from breqy.domain.models import Session
from breqy.engine.event_writer import EventWriter
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


@pytest.mark.asyncio
async def test_event_writer_writes_single_event(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    writer = EventWriter(event_repo)

    e = MessageSentEvent(
        session_id=session.id, message_id="msg_1", role="user", content="Hello"
    )
    await writer.start()
    await writer.write(e)
    await writer.stop()

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 1
    assert events[0].event_id == e.event_id


@pytest.mark.asyncio
async def test_event_writer_handles_concurrent_writes(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    writer = EventWriter(event_repo)
    await writer.start()

    # Fire 20 events concurrently from multiple producers
    evts = [
        MessageSentEvent(
            session_id=session.id,
            message_id=f"msg_{i}",
            role="user",
            content=f"msg {i}",
        )
        for i in range(20)
    ]
    await asyncio.gather(*[writer.write(e) for e in evts])
    await writer.stop()

    stored = await event_repo.list_by_session(session.id, limit=50)
    assert len(stored) == 20


@pytest.mark.asyncio
async def test_event_writer_stop_flushes_queue(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    writer = EventWriter(event_repo)
    await writer.start()

    for i in range(5):
        e = MessageSentEvent(
            session_id=session.id,
            message_id=f"msg_{i}",
            role="user",
            content=f"msg {i}",
        )
        await writer.write(e)

    await writer.stop()  # Must flush all before returning

    stored = await event_repo.list_by_session(session.id, limit=10)
    assert len(stored) == 5

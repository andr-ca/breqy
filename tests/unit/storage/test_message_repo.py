"""Tests for SQLite message repository."""

import pytest

from breqy.domain.enums import MessageRole
from breqy.domain.models import Message, Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository


@pytest.mark.asyncio
async def test_create_and_list_messages(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    msg_repo = SqliteMessageRepository(db_connection)
    m1 = Message(session_id=session.id, role=MessageRole.USER, content="Hello")
    m2 = Message(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content="Hi there",
        agent_id="agent_breqy",
    )
    await msg_repo.create(m1)
    await msg_repo.create(m2)

    messages = await msg_repo.list_by_session(session.id)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there"
    assert messages[1].agent_id == "agent_breqy"


@pytest.mark.asyncio
async def test_list_messages_respects_limit(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    msg_repo = SqliteMessageRepository(db_connection)
    for i in range(10):
        msg = Message(session_id=session.id, role=MessageRole.USER, content=f"msg {i}")
        await msg_repo.create(msg)

    messages = await msg_repo.list_by_session(session.id, limit=3)
    assert len(messages) == 3


@pytest.mark.asyncio
async def test_message_roundtrip(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    msg_repo = SqliteMessageRepository(db_connection)
    m = Message(session_id=session.id, role=MessageRole.SYSTEM, content="System init")
    await msg_repo.create(m)

    messages = await msg_repo.list_by_session(session.id)
    assert len(messages) == 1
    assert messages[0].id == m.id
    assert messages[0].role == MessageRole.SYSTEM
    assert messages[0].content == "System init"

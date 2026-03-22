"""Tests for SessionManager."""
from __future__ import annotations

import pytest

from breqy.engine.session_manager import SessionManager
from breqy.domain.enums import MessageRole, SessionStatus
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository


@pytest.mark.asyncio
async def test_create_session(db_connection):
    """create_session returns an ACTIVE session with the given agent_id."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    assert session.status == SessionStatus.ACTIVE
    assert session.primary_agent_id == "breqy"

    retrieved = await manager.get_session(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id


@pytest.mark.asyncio
async def test_list_sessions(db_connection):
    """list_sessions returns all created sessions."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    await manager.create_session(agent_id="breqy")
    await manager.create_session(agent_id="breqy")

    sessions = await manager.list_sessions()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_add_message(db_connection):
    """add_message persists a message and it appears in get_messages."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    msg = await manager.add_message(session.id, MessageRole.USER, "Hello")

    assert msg.content == "Hello"
    messages = await manager.get_messages(session.id)
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_close_session(db_connection):
    """close_session sets session status to CLOSED."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    await manager.close_session(session.id)

    result = await manager.get_session(session.id)
    assert result is not None
    assert result.status == SessionStatus.CLOSED

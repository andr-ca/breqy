"""Tests for SessionManager."""
from __future__ import annotations

import pytest

from breqy.domain.enums import MessageRole, SessionStatus
from breqy.domain.errors import SessionNotFoundError
from breqy.engine.session_manager import SessionManager
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.participant_repo import SqliteParticipantRepository
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


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


# --- Task 5b: restore_active_sessions ---


@pytest.mark.asyncio
async def test_restore_active_sessions(db_connection):
    """restore_active_sessions returns only active sessions, not closed ones."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    await manager.create_session(agent_id="agent-a")
    await manager.create_session(agent_id="agent-b")
    s3 = await manager.create_session(agent_id="agent-c")
    await manager.close_session(s3.id)

    active = await manager.restore_active_sessions()
    assert len(active) == 2
    assert all(s.status == SessionStatus.ACTIVE for s in active)


# --- Task 5c: workspace path management ---


@pytest.mark.asyncio
async def test_set_workspace_paths_valid(db_connection, tmp_dir):
    """set_workspace_paths stores valid paths that can be read back."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")

    path1 = tmp_dir / "workspace_a"
    path1.mkdir()
    path2 = tmp_dir / "workspace_b"
    path2.mkdir()

    await manager.set_workspace_paths(session.id, [str(path1), str(path2)])

    result = await manager.get_workspace_paths(session.id)
    assert result == [str(path1), str(path2)]


@pytest.mark.asyncio
async def test_set_workspace_paths_invalid(db_connection):
    """set_workspace_paths raises ValueError for non-existent paths."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")

    with pytest.raises(ValueError, match="Workspace path does not exist"):
        await manager.set_workspace_paths(session.id, ["/nonexistent/path/xyz"])


@pytest.mark.asyncio
async def test_get_workspace_paths(db_connection, tmp_dir):
    """get_workspace_paths returns paths previously set."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")

    ws = tmp_dir / "ws"
    ws.mkdir()
    await manager.set_workspace_paths(session.id, [str(ws)])

    paths = await manager.get_workspace_paths(session.id)
    assert paths == [str(ws)]


@pytest.mark.asyncio
async def test_get_workspace_paths_not_found(db_connection):
    """get_workspace_paths raises SessionNotFoundError for missing session."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    with pytest.raises(SessionNotFoundError):
        await manager.get_workspace_paths("ses_nonexistent")


# --- Task 5d: participant lifecycle hooks ---


@pytest.mark.asyncio
async def test_add_participant(db_connection):
    """add_participant creates and persists a participant."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)
    manager = SessionManager(session_repo, message_repo, participant_repo=participant_repo)

    session = await manager.create_session(agent_id="breqy")
    participant = await manager.add_participant(session.id, "helper-agent")

    assert participant.session_id == session.id
    assert participant.agent_id == "helper-agent"
    assert participant.left_at is None

    participants = await manager.get_session_participants(session.id)
    assert len(participants) == 1
    assert participants[0].id == participant.id


@pytest.mark.asyncio
async def test_remove_participant(db_connection):
    """remove_participant sets left_at on an active participant."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)
    manager = SessionManager(session_repo, message_repo, participant_repo=participant_repo)

    session = await manager.create_session(agent_id="breqy")
    await manager.add_participant(session.id, "helper-agent")
    await manager.remove_participant(session.id, "helper-agent")

    # After removal, no active participants
    active = await manager.get_session_participants(session.id)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_remove_participant_not_found(db_connection):
    """remove_participant does not raise for non-joined agent (just warns)."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)
    manager = SessionManager(session_repo, message_repo, participant_repo=participant_repo)

    session = await manager.create_session(agent_id="breqy")
    # Should not raise — just log a warning
    await manager.remove_participant(session.id, "unknown-agent")


@pytest.mark.asyncio
async def test_get_session_participants(db_connection):
    """get_session_participants returns only active participants."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    participant_repo = SqliteParticipantRepository(db_connection)
    manager = SessionManager(session_repo, message_repo, participant_repo=participant_repo)

    session = await manager.create_session(agent_id="breqy")
    await manager.add_participant(session.id, "agent-a")
    await manager.add_participant(session.id, "agent-b")
    await manager.remove_participant(session.id, "agent-a")

    active = await manager.get_session_participants(session.id)
    assert len(active) == 1
    assert active[0].agent_id == "agent-b"


@pytest.mark.asyncio
async def test_participant_repo_not_configured(db_connection):
    """Calling participant methods without participant_repo raises RuntimeError."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")

    with pytest.raises(RuntimeError, match="ParticipantRepository not configured"):
        await manager.add_participant(session.id, "some-agent")

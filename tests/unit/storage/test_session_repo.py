"""Tests for SQLite session repository."""

import pytest

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


@pytest.mark.asyncio
async def test_create_and_get_session(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await repo.create(session)

    result = await repo.get(session.id)
    assert result is not None
    assert result.id == session.id
    assert result.primary_agent_id == "agent_breqy"
    assert result.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_nonexistent_session(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    result = await repo.get("ses_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_active_sessions(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    s1 = Session(primary_agent_id="agent_breqy")
    s2 = Session(primary_agent_id="agent_breqy")
    s3 = Session(primary_agent_id="agent_breqy", status=SessionStatus.CLOSED)

    await repo.create(s1)
    await repo.create(s2)
    await repo.create(s3)

    active = await repo.list_active()
    assert len(active) == 2


@pytest.mark.asyncio
async def test_update_session_status(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await repo.create(session)

    await repo.update_status(session.id, SessionStatus.SUSPENDED)
    result = await repo.get(session.id)
    assert result is not None
    assert result.status == SessionStatus.SUSPENDED


@pytest.mark.asyncio
async def test_update_session_timestamp(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await repo.create(session)
    original = (await repo.get(session.id)).updated_at

    import asyncio
    await asyncio.sleep(0.01)
    await repo.update_timestamp(session.id)
    updated = (await repo.get(session.id)).updated_at
    assert updated >= original


@pytest.mark.asyncio
async def test_session_roundtrip_workspace_paths(db_connection) -> None:
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy", workspace_paths=["/home/user", "/tmp"])
    await repo.create(session)

    result = await repo.get(session.id)
    assert result is not None
    assert result.workspace_paths == ["/home/user", "/tmp"]

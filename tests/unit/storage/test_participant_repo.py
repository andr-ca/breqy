"""Tests for SQLite participant repository."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from breqy.domain.models import Participant, Session
from breqy.storage.interfaces import ParticipantRepository
from breqy.storage.sqlite.participant_repo import SqliteParticipantRepository
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


async def _create_session(db_connection, agent_id: str = "agt_breqy") -> Session:
    """Helper: insert a session so FK constraints pass."""
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id=agent_id)
    await repo.create(session)
    return session


# ---------- interface conformance ----------


def test_sqlite_participant_repo_implements_interface() -> None:
    """SqliteParticipantRepository must be a concrete ParticipantRepository."""
    assert issubclass(SqliteParticipantRepository, ParticipantRepository)


# ---------- create + get ----------


@pytest.mark.asyncio
async def test_create_and_get_participant(db_connection) -> None:
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    participant = Participant(session_id=session.id, agent_id="agt_one")
    await repo.create(participant)

    result = await repo.get(participant.id)
    assert result is not None
    assert result.id == participant.id
    assert result.session_id == session.id
    assert result.agent_id == "agt_one"
    assert result.left_at is None


@pytest.mark.asyncio
async def test_get_nonexistent_participant(db_connection) -> None:
    repo = SqliteParticipantRepository(db_connection)
    result = await repo.get("par_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_create_preserves_datetime_roundtrip(db_connection) -> None:
    """joined_at must survive ISO-8601 serialization round-trip."""
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    now = datetime.now(timezone.utc)
    participant = Participant(session_id=session.id, agent_id="agt_dt", joined_at=now)
    await repo.create(participant)

    result = await repo.get(participant.id)
    assert result is not None
    # Tolerate microsecond loss from ISO round-trip
    assert abs((result.joined_at - now).total_seconds()) < 0.001


# ---------- list_by_session ----------


@pytest.mark.asyncio
async def test_list_by_session(db_connection) -> None:
    s1 = await _create_session(db_connection, "agt_a")
    s2 = await _create_session(db_connection, "agt_b")
    repo = SqliteParticipantRepository(db_connection)

    p1 = Participant(session_id=s1.id, agent_id="agt_one")
    p2 = Participant(session_id=s1.id, agent_id="agt_two")
    p3 = Participant(session_id=s2.id, agent_id="agt_three")
    await repo.create(p1)
    await repo.create(p2)
    await repo.create(p3)

    results = await repo.list_by_session(s1.id)
    assert len(results) == 2
    ids = {r.id for r in results}
    assert p1.id in ids
    assert p2.id in ids


@pytest.mark.asyncio
async def test_list_by_session_empty(db_connection) -> None:
    repo = SqliteParticipantRepository(db_connection)
    results = await repo.list_by_session("ses_nonexistent")
    assert results == []


# ---------- get_active_by_session ----------


@pytest.mark.asyncio
async def test_get_active_by_session(db_connection) -> None:
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    p_active = Participant(session_id=session.id, agent_id="agt_active")
    p_left = Participant(
        session_id=session.id,
        agent_id="agt_left",
        left_at=datetime.now(timezone.utc),
    )
    await repo.create(p_active)
    await repo.create(p_left)

    active = await repo.get_active_by_session(session.id)
    assert len(active) == 1
    assert active[0].id == p_active.id
    assert active[0].left_at is None


@pytest.mark.asyncio
async def test_get_active_by_session_empty(db_connection) -> None:
    repo = SqliteParticipantRepository(db_connection)
    results = await repo.get_active_by_session("ses_nonexistent")
    assert results == []


# ---------- get_by_agent_and_session ----------


@pytest.mark.asyncio
async def test_get_by_agent_and_session(db_connection) -> None:
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    participant = Participant(session_id=session.id, agent_id="agt_lookup")
    await repo.create(participant)

    result = await repo.get_by_agent_and_session("agt_lookup", session.id)
    assert result is not None
    assert result.id == participant.id
    assert result.agent_id == "agt_lookup"


@pytest.mark.asyncio
async def test_get_by_agent_and_session_returns_most_recent(db_connection) -> None:
    """When multiple records exist, return the one with the latest joined_at."""
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    older = Participant(
        session_id=session.id,
        agent_id="agt_multi",
        joined_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    newer = Participant(
        session_id=session.id,
        agent_id="agt_multi",
        joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(older)
    await repo.create(newer)

    result = await repo.get_by_agent_and_session("agt_multi", session.id)
    assert result is not None
    assert result.id == newer.id


@pytest.mark.asyncio
async def test_get_by_agent_and_session_not_found(db_connection) -> None:
    repo = SqliteParticipantRepository(db_connection)
    result = await repo.get_by_agent_and_session("agt_nope", "ses_nope")
    assert result is None


# ---------- set_left_at ----------


@pytest.mark.asyncio
async def test_set_left_at(db_connection) -> None:
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    participant = Participant(session_id=session.id, agent_id="agt_leaving")
    await repo.create(participant)

    leave_time = datetime.now(timezone.utc)
    await repo.set_left_at(participant.id, leave_time)

    result = await repo.get(participant.id)
    assert result is not None
    assert result.left_at is not None
    assert abs((result.left_at - leave_time).total_seconds()) < 0.001


@pytest.mark.asyncio
async def test_set_left_at_removes_from_active(db_connection) -> None:
    """After set_left_at, participant should no longer appear in active list."""
    session = await _create_session(db_connection)
    repo = SqliteParticipantRepository(db_connection)

    participant = Participant(session_id=session.id, agent_id="agt_depart")
    await repo.create(participant)

    active_before = await repo.get_active_by_session(session.id)
    assert len(active_before) == 1

    await repo.set_left_at(participant.id, datetime.now(timezone.utc))

    active_after = await repo.get_active_by_session(session.id)
    assert len(active_after) == 0

"""Tests for SQLite approval repository."""

import pytest

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest, Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository


@pytest.mark.asyncio
async def test_create_and_get_approval_request(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    req = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Execute: rm /tmp/file",
    )
    await repo.create_request(req)

    result = await repo.get_request(req.id)
    assert result is not None
    assert result.description == "Execute: rm /tmp/file"
    assert result.status == ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_get_nonexistent_request(db_connection) -> None:
    repo = SqliteApprovalRepository(db_connection)
    result = await repo.get_request("apr_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_pending_by_session(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    r1 = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_1",
        description="Action 1",
    )
    r2 = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_2",
        description="Action 2",
    )
    await repo.create_request(r1)
    await repo.create_request(r2)

    pending = await repo.get_pending_by_session(session.id)
    assert len(pending) == 2


@pytest.mark.asyncio
async def test_update_request_status(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    req = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Test",
    )
    await repo.create_request(req)
    await repo.update_request_status(req.id, ApprovalStatus.GRANTED)

    result = await repo.get_request(req.id)
    assert result is not None
    assert result.status == ApprovalStatus.GRANTED


@pytest.mark.asyncio
async def test_create_decision_and_get_grants(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    req = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Execute: ls",
    )
    await repo.create_request(req)

    decision = ApprovalDecision(
        request_id=req.id,
        granted=True,
        extend_to_session=True,
    )
    await repo.create_decision(decision)
    await repo.update_request_status(req.id, ApprovalStatus.GRANTED)

    grants = await repo.get_session_grants(session.id)
    assert len(grants) == 1
    assert grants[0].extend_to_session is True
    assert grants[0].granted is True

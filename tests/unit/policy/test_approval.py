"""Tests for ApprovalService — in-memory approval orchestration."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from breqy.domain.enums import ApprovalGrantScope, ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalGrant, ApprovalRequest
from breqy.policy.approval import ApprovalService


def _make_repo():
    """Create a mock ApprovalRepository."""
    repo = AsyncMock()
    repo.get_session_grants = AsyncMock(return_value=[])
    repo.get_grants = AsyncMock(return_value=[])
    repo.has_grant = AsyncMock(return_value=False)
    repo.create_grant = AsyncMock()
    repo.create_request = AsyncMock()
    repo.create_decision = AsyncMock()
    repo.update_request_status = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_request_approval_returns_request_id():
    """request_approval returns a non-empty request ID."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_1",
        agent_id="agt_1",
        tool_invocation_id="inv_1",
        description="Run shell command",
    )
    assert request_id.startswith("apr_")
    repo.create_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_approval_persists_grant_key():
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_1",
        agent_id="agt_1",
        tool_invocation_id="inv_1",
        description="Browser submit on google.com",
        grant_key="browser:submit:google.com",
    )
    assert request_id.startswith("apr_")
    created_request = repo.create_request.await_args.args[0]
    assert created_request.grant_key == "browser:submit:google.com"


@pytest.mark.asyncio
async def test_decide_granted_resolves_wait():
    """decide(granted=True) unblocks wait_for_decision and returns GRANTED."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_2",
        agent_id="agt_1",
        tool_invocation_id="inv_2",
        description="Write file",
    )

    async def grant():
        await asyncio.sleep(0.01)
        await service.decide(request_id, granted=True)

    asyncio.create_task(grant())
    result = await service.wait_for_decision(request_id, timeout=2.0)
    assert result == ApprovalStatus.GRANTED
    repo.create_decision.assert_awaited_once()
    repo.update_request_status.assert_awaited_once_with(request_id, ApprovalStatus.GRANTED)


@pytest.mark.asyncio
async def test_decide_denied_resolves_wait():
    """decide(granted=False) unblocks wait_for_decision and returns DENIED."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_3",
        agent_id="agt_1",
        tool_invocation_id="inv_3",
        description="Delete files",
    )

    async def deny():
        await asyncio.sleep(0.01)
        await service.decide(request_id, granted=False)

    asyncio.create_task(deny())
    result = await service.wait_for_decision(request_id, timeout=2.0)
    assert result == ApprovalStatus.DENIED
    repo.update_request_status.assert_awaited_once_with(request_id, ApprovalStatus.DENIED)


@pytest.mark.asyncio
async def test_wait_for_decision_times_out():
    """wait_for_decision returns EXPIRED on timeout without raising."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_4",
        agent_id="agt_1",
        tool_invocation_id="inv_4",
        description="Network access",
    )
    result = await service.wait_for_decision(request_id, timeout=0.05)
    assert result == ApprovalStatus.EXPIRED
    repo.update_request_status.assert_awaited_with(request_id, ApprovalStatus.EXPIRED)


@pytest.mark.asyncio
async def test_extend_to_session_caches_grant():
    """decide(extend_to_session=True) stores session grant in memory."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_5",
        agent_id="agt_1",
        tool_invocation_id="inv_5",
        description="Run shell",
        grant_key="tool:shell",
    )
    await service.decide(request_id, granted=True, grant_scope=ApprovalGrantScope.SESSION)
    assert service.has_grant("ses_5", "tool:shell") is True


@pytest.mark.asyncio
async def test_forever_grant_persists_and_applies_across_sessions():
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_forever",
        agent_id="agt_1",
        tool_invocation_id="inv_forever",
        description="Browser submit on google.com",
        grant_key="browser:submit:google.com",
    )

    await service.decide(request_id, granted=True, grant_scope=ApprovalGrantScope.FOREVER)

    assert service.has_grant("ses_forever", "browser:submit:google.com") is True
    assert service.has_grant("ses_other", "browser:submit:google.com") is True
    repo.create_grant.assert_awaited()


def test_has_session_grant_returns_false_when_not_granted():
    """has_session_grant returns False when no session grant exists."""
    repo = _make_repo()
    service = ApprovalService(repo)
    assert service.has_session_grant("ses_x", "Run shell") is False


@pytest.mark.asyncio
async def test_decide_raises_for_unknown_request_id():
    """decide() with an unknown request_id raises ValueError."""
    repo = _make_repo()
    service = ApprovalService(repo)
    with pytest.raises(ValueError, match="No pending approval"):
        await service.decide("apr_nonexistent", granted=True)


@pytest.mark.asyncio
async def test_wait_for_decision_raises_for_unknown_request_id():
    """wait_for_decision() with unknown request_id raises ValueError."""
    repo = _make_repo()
    service = ApprovalService(repo)
    with pytest.raises(ValueError, match="No pending approval"):
        await service.wait_for_decision("apr_nonexistent", timeout=1.0)


@pytest.mark.asyncio
async def test_load_session_grants_populates_cache():
    """load_session_grants() fetches extend_to_session decisions from DB and caches them."""
    repo = _make_repo()

    # Set up mock: one extend_to_session decision exists in DB
    decision = ApprovalDecision(
        request_id="apr_existing",
        granted=True,
        grant_scope=ApprovalGrantScope.SESSION,
    )
    request = ApprovalRequest(
        id="apr_existing",
        session_id="ses_reload",
        agent_id="agt_1",
        tool_invocation_id="inv_existing",
        description="Run shell",
        grant_key="tool:shell",
    )
    repo.get_session_grants = AsyncMock(return_value=[decision])
    repo.get_request = AsyncMock(return_value=request)
    repo.get_grants = AsyncMock(
        side_effect=lambda session_id=None: (
            [
                ApprovalGrant(
                    session_id="ses_reload",
                    grant_key="tool:shell",
                    scope=ApprovalGrantScope.SESSION,
                )
            ]
            if session_id == "ses_reload"
            else [
                ApprovalGrant(
                    session_id=None,
                    grant_key="browser:extract:google.com",
                    scope=ApprovalGrantScope.FOREVER,
                )
            ]
        )
    )

    service = ApprovalService(repo)
    # Cache is empty before load
    assert service.has_session_grant("ses_reload", "Run shell") is False

    await service.load_session_grants("ses_reload")

    # Cache is populated after load
    assert service.has_grant("ses_reload", "tool:shell") is True


@pytest.mark.asyncio
async def test_denied_with_extend_to_session_does_not_cache():
    """decide(granted=False, extend_to_session=True) does not create a session grant."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_6",
        agent_id="agt_1",
        tool_invocation_id="inv_6",
        description="Run shell",
        grant_key="tool:shell",
    )
    await service.decide(request_id, granted=False, grant_scope=ApprovalGrantScope.SESSION)
    assert service.has_grant("ses_6", "tool:shell") is False


@pytest.mark.asyncio
async def test_timeout_sets_expired_status():
    """wait_for_decision timeout marks request as EXPIRED in DB."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_7",
        agent_id="agt_1",
        tool_invocation_id="inv_7",
        description="Network access",
    )
    result = await service.wait_for_decision(request_id, timeout=0.05)
    assert result == ApprovalStatus.EXPIRED
    repo.update_request_status.assert_awaited_with(request_id, ApprovalStatus.EXPIRED)


@pytest.mark.asyncio
async def test_decide_twice_raises_on_second_call():
    """decide() called twice on the same request_id raises ValueError on second call.

    After the first decide() prunes _pending, the second call sees a missing
    request and raises ValueError with "No pending approval". This is equivalent
    to 'already decided' from the caller's perspective.
    """
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_8",
        agent_id="agt_1",
        tool_invocation_id="inv_8",
        description="Run shell",
    )
    await service.decide(request_id, granted=True)
    with pytest.raises(ValueError):
        await service.decide(request_id, granted=False)

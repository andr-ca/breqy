# Phase 4 Plan 02: ApprovalService

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `ApprovalService` — an async in-memory approval orchestrator that creates approval requests (persisted via `ApprovalRepository`), waits for user decisions, supports session-scoped "approve for rest of session" grants, and checks cached session grants to skip re-prompting.

**Architecture:** One class `ApprovalService` in `breqy/policy/approval.py`. It depends on `ApprovalRepository` (injected) for persistence and uses `asyncio.Event` internally to coordinate async waiting. Session-scoped grants are checked via an in-memory cache and also read from the DB via `get_session_grants`. No network or A2A involved.

> **Prerequisite:** Phase 4 Plan 01 must be complete (creates `breqy/policy/` package).

> **Package location note:** `ApprovalService` is placed in `breqy/policy/approval.py` (co-located with policy logic) rather than a separate `breqy/approval/` package, to keep Phase 4 cohesive.

**Tech Stack:** Python 3.12, asyncio, pydantic v2, aiosqlite (via existing `SqliteApprovalRepository`)

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Run tests with:** `uv run pytest`

---

## Key Domain Facts (read before coding)

From `breqy/domain/models.py`:
- `ApprovalRequest(id, session_id, agent_id, tool_invocation_id, description, status, created_at, expires_at)`
- `ApprovalDecision(id, request_id, granted, extend_to_session, reason, decided_at)`

From `breqy/domain/enums.py`:
- `ApprovalStatus.PENDING`, `GRANTED`, `DENIED`, `EXPIRED`

From `breqy/storage/interfaces.py` — `ApprovalRepository` ABC:
- `create_request(request)` — persist new request
- `create_decision(decision)` — persist decision
- `get_request(request_id) -> ApprovalRequest | None`
- `get_pending_by_session(session_id) -> list[ApprovalRequest]`
- `update_request_status(request_id, status)` — update DB status
- `get_session_grants(session_id) -> list[ApprovalDecision]` — returns extend_to_session=True decisions

The existing `SqliteApprovalRepository` in `breqy/storage/sqlite/approval_repo.py` implements this interface.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `breqy/policy/approval.py` | Create | `ApprovalService` — create/decide/wait/session-grant logic |
| `tests/unit/policy/test_approval.py` | Create | 7 TDD tests for ApprovalService |

---

## Task 1: ApprovalService

**Files:**
- Create: `breqy/policy/approval.py`
- Create: `tests/unit/policy/test_approval.py`

- [ ] **Step 1: Write failing tests for ApprovalService**

Create `tests/unit/policy/test_approval.py`:

```python
"""Tests for ApprovalService — in-memory approval orchestration."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest
from breqy.policy.approval import ApprovalService


def _make_repo():
    """Create a mock ApprovalRepository."""
    repo = AsyncMock()
    repo.get_session_grants = AsyncMock(return_value=[])
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
async def test_decide_granted_resolves_wait():
    """decide(granted=True) unblocks wait_for_decision and returns True."""
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
    assert result is True
    repo.create_decision.assert_awaited_once()
    repo.update_request_status.assert_awaited_once_with(request_id, ApprovalStatus.GRANTED)


@pytest.mark.asyncio
async def test_decide_denied_resolves_wait():
    """decide(granted=False) unblocks wait_for_decision and returns False."""
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
    assert result is False
    repo.update_request_status.assert_awaited_once_with(request_id, ApprovalStatus.DENIED)


@pytest.mark.asyncio
async def test_wait_for_decision_times_out():
    """wait_for_decision returns False on timeout without raising."""
    repo = _make_repo()
    service = ApprovalService(repo)
    request_id = await service.request_approval(
        session_id="ses_4",
        agent_id="agt_1",
        tool_invocation_id="inv_4",
        description="Network access",
    )
    result = await service.wait_for_decision(request_id, timeout=0.05)
    assert result is False


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
    )
    await service.decide(request_id, granted=True, extend_to_session=True)
    assert service.has_session_grant("ses_5", "Run shell") is True


@pytest.mark.asyncio
async def test_has_session_grant_returns_false_when_not_granted():
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
async def test_load_session_grants_populates_cache():
    """load_session_grants() fetches extend_to_session decisions from DB and caches them."""
    repo = _make_repo()

    # Set up mock: one extend_to_session decision exists in DB
    decision = ApprovalDecision(
        request_id="apr_existing",
        granted=True,
        extend_to_session=True,
    )
    request = ApprovalRequest(
        id="apr_existing",
        session_id="ses_reload",
        agent_id="agt_1",
        tool_invocation_id="inv_existing",
        description="Run shell",
    )
    repo.get_session_grants = AsyncMock(return_value=[decision])
    repo.get_request = AsyncMock(return_value=request)

    service = ApprovalService(repo)
    # Cache is empty before load
    assert service.has_session_grant("ses_reload", "Run shell") is False

    await service.load_session_grants("ses_reload")

    # Cache is populated after load
    assert service.has_session_grant("ses_reload", "Run shell") is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/policy/test_approval.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.policy.approval'`

- [ ] **Step 3: Create `breqy/policy/approval.py`**

```python
"""ApprovalService: async approval orchestration with session-scoped grants.

Responsibilities:
- Create approval requests (persisted via ApprovalRepository)
- Allow TUI/user to record decisions
- Async wait for a decision with configurable timeout
- Cache session-wide grants to avoid repeat prompting
"""
from __future__ import annotations

import asyncio
import logging

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest
from breqy.domain.ids import generate_prefixed_id
from breqy.storage.interfaces import ApprovalRepository

logger = logging.getLogger(__name__)


class _PendingApproval:
    """Internal state for a single in-flight approval request."""

    def __init__(self, request: ApprovalRequest) -> None:
        self.request = request
        self.decided = asyncio.Event()
        self.granted: bool = False
        self.extend_to_session: bool = False


class ApprovalService:
    """Manages approval requests and decisions.

    Thread-safety: designed for single-thread asyncio use only.
    """

    def __init__(self, repo: ApprovalRepository) -> None:
        self._repo = repo
        self._pending: dict[str, _PendingApproval] = {}
        # session_id -> set of granted descriptions (in-memory cache)
        self._session_grants: dict[str, set[str]] = {}

    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
    ) -> str:
        """Create and persist an approval request. Returns the request ID."""
        request = ApprovalRequest(
            id=generate_prefixed_id("apr"),
            session_id=session_id,
            agent_id=agent_id,
            tool_invocation_id=tool_invocation_id,
            description=description,
        )
        await self._repo.create_request(request)
        self._pending[request.id] = _PendingApproval(request)
        logger.info("Approval requested: %s — %s", request.id, description)
        return request.id

    async def decide(
        self,
        request_id: str,
        granted: bool,
        extend_to_session: bool = False,
        reason: str = "",
    ) -> None:
        """Record a user decision on a pending approval request."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        pending.granted = granted
        pending.extend_to_session = extend_to_session

        # Persist decision
        decision = ApprovalDecision(
            request_id=request_id,
            granted=granted,
            extend_to_session=extend_to_session,
            reason=reason,
        )
        await self._repo.create_decision(decision)

        # Update request status in DB
        status = ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED
        await self._repo.update_request_status(request_id, status)

        # Cache session grant if applicable
        if granted and extend_to_session:
            grants = self._session_grants.setdefault(pending.request.session_id, set())
            grants.add(pending.request.description)

        pending.decided.set()
        logger.info(
            "Approval %s: %s (extend=%s)",
            "granted" if granted else "denied",
            request_id,
            extend_to_session,
        )

    async def wait_for_decision(self, request_id: str, timeout: float = 300.0) -> bool:
        """Wait for a user decision. Returns True if granted, False if denied/timeout."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        try:
            await asyncio.wait_for(pending.decided.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Approval timed out: %s", request_id)
            return False

        return pending.granted

    def has_session_grant(self, session_id: str, description: str) -> bool:
        """Return True if a session-wide grant exists for this description."""
        grants = self._session_grants.get(session_id, set())
        return description in grants

    async def load_session_grants(self, session_id: str) -> None:
        """Populate in-memory session grant cache from DB (call on resume)."""
        decisions = await self._repo.get_session_grants(session_id)
        for decision in decisions:
            request = await self._repo.get_request(decision.request_id)
            if request is not None:
                grants = self._session_grants.setdefault(session_id, set())
                grants.add(request.description)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/policy/test_approval.py -v
```
Expected: 8 passed

- [ ] **Step 5: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```
Expected: all prior + 8 new tests pass

- [ ] **Step 6: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/policy/approval.py tests/unit/policy/test_approval.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(policy): add ApprovalService with async wait, session grants, and DB persistence"
```

---

## Final Verification

```bash
uv run pytest tests/unit/policy/ -v
```
Expected: 21 tests pass (8 evaluator + 5 filesystem + 8 approval), full suite green.

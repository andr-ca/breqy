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

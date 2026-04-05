"""ApprovalService: async approval orchestration with structured approval grants.

Responsibilities:
- Create approval requests (persisted via ApprovalRepository)
- Allow TUI/user to record decisions
- Async wait for a decision with configurable timeout
- Cache session and forever grants to avoid repeat prompting
"""
from __future__ import annotations

import asyncio

import structlog

from breqy.domain.enums import ApprovalGrantScope, ApprovalStatus
from breqy.domain.ids import generate_prefixed_id
from breqy.domain.models import ApprovalDecision, ApprovalGrant, ApprovalRequest
from breqy.storage.interfaces import ApprovalRepository

logger = structlog.get_logger(__name__)


class _PendingApproval:
    """Internal state for a single in-flight approval request."""

    def __init__(self, request: ApprovalRequest) -> None:
        self.request = request
        self.decided = asyncio.Event()
        self.status: ApprovalStatus = ApprovalStatus.PENDING
        self.grant_scope: ApprovalGrantScope = ApprovalGrantScope.ONCE
        self.cleanup_task: asyncio.Task[None] | None = None


class ApprovalService:
    """Manages approval requests and decisions.

    Thread-safety: designed for single-thread asyncio use only.
    """

    def __init__(
        self,
        repo: ApprovalRepository,
        *,
        decided_request_ttl_seconds: float = 300.0,
    ) -> None:
        self._repo = repo
        self._decided_request_ttl_seconds = decided_request_ttl_seconds
        self._pending: dict[str, _PendingApproval] = {}
        # session_id -> set of granted keys/descriptions (in-memory cache)
        self._session_grants: dict[str, set[str]] = {}
        self._forever_grants: set[str] = set()
        self._loaded_sessions: set[str] = set()
        self._forever_loaded = False

    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
        grant_key: str = "",
    ) -> str:
        """Create and persist an approval request. Returns the request ID."""
        request = ApprovalRequest(
            id=generate_prefixed_id("apr"),
            session_id=session_id,
            agent_id=agent_id,
            tool_invocation_id=tool_invocation_id,
            description=description,
            grant_key=grant_key,
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
        grant_scope: ApprovalGrantScope | None = None,
        reason: str = "",
    ) -> None:
        """Record a user decision on a pending approval request."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        if pending.decided.is_set():
            raise ValueError(f"Approval already decided: {request_id}")

        pending.status = ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED
        resolved_grant_scope = (
            grant_scope
            if grant_scope is not None
            else ApprovalGrantScope.SESSION if extend_to_session else ApprovalGrantScope.ONCE
        )
        pending.grant_scope = resolved_grant_scope

        # Persist decision
        decision = ApprovalDecision(
            request_id=request_id,
            granted=granted,
            grant_scope=resolved_grant_scope,
            reason=reason,
        )
        await self._repo.create_decision(decision)

        # Update request status in DB
        status = pending.status
        await self._repo.update_request_status(request_id, status)

        grant_key = pending.request.grant_key or pending.request.description
        if granted and grant_key and resolved_grant_scope == ApprovalGrantScope.SESSION:
            grants = self._session_grants.setdefault(pending.request.session_id, set())
            grants.add(grant_key)
            await self._repo.create_grant(
                ApprovalGrant(
                    session_id=pending.request.session_id,
                    grant_key=grant_key,
                    scope=ApprovalGrantScope.SESSION,
                )
            )
        if granted and grant_key and resolved_grant_scope == ApprovalGrantScope.FOREVER:
            self._forever_grants.add(grant_key)
            await self._repo.create_grant(
                ApprovalGrant(
                    session_id=None,
                    grant_key=grant_key,
                    scope=ApprovalGrantScope.FOREVER,
                )
            )

        pending.decided.set()
        pending.cleanup_task = asyncio.create_task(
            self._prune_decided_request(request_id, delay_seconds=self._decided_request_ttl_seconds)
        )
        logger.info(
            "Approval %s: %s (scope=%s)",
            "granted" if granted else "denied",
            request_id,
            resolved_grant_scope.value,
        )

    async def wait_for_decision(
        self,
        request_id: str,
        timeout: float = 300.0,
    ) -> ApprovalStatus:
        """Wait for a user decision. Returns GRANTED, DENIED, or EXPIRED."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        try:
            await asyncio.wait_for(pending.decided.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Approval timed out: %s", request_id)
            self._pending.pop(request_id, None)
            await self._repo.update_request_status(request_id, ApprovalStatus.EXPIRED)
            return ApprovalStatus.EXPIRED

        if pending.cleanup_task is not None:
            pending.cleanup_task.cancel()
        self._pending.pop(request_id, None)
        return pending.status

    def has_session_grant(self, session_id: str, description: str) -> bool:
        """Return True if a session-wide grant exists for this description."""
        return self.has_grant(session_id, description)

    def has_grant(self, session_id: str, grant_key: str) -> bool:
        session_grants = self._session_grants.get(session_id, set())
        return grant_key in session_grants or grant_key in self._forever_grants

    async def ensure_grants_loaded(self, session_id: str) -> None:
        if session_id not in self._loaded_sessions:
            for grant in await self._repo.get_grants(session_id):
                session_grants = self._session_grants.setdefault(session_id, set())
                session_grants.add(grant.grant_key)
            self._loaded_sessions.add(session_id)
        if not self._forever_loaded:
            for grant in await self._repo.get_grants():
                if grant.scope == ApprovalGrantScope.FOREVER:
                    self._forever_grants.add(grant.grant_key)
            self._forever_loaded = True

    async def load_session_grants(self, session_id: str) -> None:
        """Populate in-memory session grant cache from DB (call on resume)."""
        await self.ensure_grants_loaded(session_id)

    async def _prune_decided_request(self, request_id: str, *, delay_seconds: float) -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        self._pending.pop(request_id, None)

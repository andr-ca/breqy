"""OrchestratorEvent — the canonical event schema for task orchestration."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from ulid import ULID


def _ulid() -> str:
    """Generate a new ULID."""
    return str(ULID())


def _now_iso() -> str:
    """Get current UTC time in ISO8601 format."""
    return datetime.now(timezone.utc).isoformat()


class OrchestratorEvent(BaseModel):
    """Event emitted during task orchestration.

    Captures state transitions, agent spawns, artifacts, CI results, rate limits,
    rework loops, and errors. Each event is immutable and timestamped.
    """

    event_id: str = Field(default_factory=_ulid)
    timestamp: str = Field(default_factory=_now_iso)
    task_id: str
    event_type: str  # state_transition | agent_spawn | agent_complete | artifact_written |
    # ci_poll | ci_result | rate_limit | rework_loop | blocked | error |
    # dependency_wait | stale_warning | retry_pending | task_cancelled
    from_state: str | None = None
    to_state: str | None = None
    role: str | None = None
    agent_type: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    notes: str = ""

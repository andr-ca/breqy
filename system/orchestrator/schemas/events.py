from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from ulid import ULID


def _ulid() -> str:
    return str(ULID())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestratorEvent(BaseModel):
    event_id: str = Field(default_factory=_ulid)
    timestamp: str = Field(default_factory=_now_iso)
    task_id: str
    event_type: str   # state_transition | agent_spawn | agent_complete | artifact_written |
                      # ci_poll | ci_result | rate_limit | rework_loop | blocked | error |
                      # dependency_wait | stale_warning | retry_pending
    from_state: str | None = None
    to_state: str | None = None
    role: str | None = None
    agent_type: str | None = None
    artifact_paths: list[str] = []
    notes: str = ""

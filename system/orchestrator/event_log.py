"""EventLog — append-only JSONL event writer for task orchestration."""
from __future__ import annotations

from pathlib import Path

from system.orchestrator.schemas.events import OrchestratorEvent


class EventLog:
    """Append-only JSONL writer. Thread-safe for single-writer use."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: OrchestratorEvent) -> None:
        with self._path.open("a") as f:
            f.write(event.model_dump_json() + "\n")

    def tail(self, n: int) -> list[OrchestratorEvent]:
        if not self._path.exists():
            return []
        lines = self._path.read_text().strip().splitlines()
        return [OrchestratorEvent.model_validate_json(line) for line in lines[-n:]]

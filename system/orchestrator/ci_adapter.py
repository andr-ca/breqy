"""CIAdapter — poll GitHub Actions CI runs and gate on green."""
from __future__ import annotations

import json
import subprocess
import time

from pydantic import BaseModel


class CiRun(BaseModel):
    run_id: int
    status: str
    conclusion: str | None
    branch: str


class CIAdapter:
    """Polls GitHub Actions runs for a branch and waits for a green result."""

    def __init__(
        self,
        repo: str,
        poll_interval_seconds: int = 60,
        event_log=None,
        task_id: str = "",
    ) -> None:
        self._repo = repo
        self._poll_interval = poll_interval_seconds
        self._log = event_log
        self._task_id = task_id

    def _emit(self, event_type: str, notes: str = "") -> None:
        if self._log:
            from system.orchestrator.schemas.events import OrchestratorEvent
            self._log.append(OrchestratorEvent(
                task_id=self._task_id, event_type=event_type, notes=notes
            ))

    def get_latest_run(self, branch: str) -> CiRun | None:
        """Return the most recent CI run for the given branch, or None."""
        result = subprocess.run(
            ["gh", "run", "list", "--repo", self._repo,
             "--branch", branch, "--json", "databaseId,status,conclusion,headBranch",
             "--limit", "1"],
            capture_output=True, text=True,
            check=False,
        )
        runs = json.loads(result.stdout or "[]")
        if not runs:
            return None
        r = runs[0]
        return CiRun(
            run_id=r["databaseId"],
            status=r["status"],
            conclusion=r.get("conclusion"),
            branch=r["headBranch"],
        )

    def wait_for_green(self, branch: str, timeout_minutes: int = 30) -> bool:
        """Block until CI passes or timeout_minutes is reached. Returns True on success."""
        deadline = time.monotonic() + timeout_minutes * 60
        while time.monotonic() < deadline:
            run = self.get_latest_run(branch)
            self._emit("ci_poll", notes=f"branch={branch} status={run.status if run else 'no-run'}")
            if run and run.status == "completed":
                success = run.conclusion == "success"
                self._emit("ci_result", notes=f"branch={branch} conclusion={run.conclusion}")
                return success
            if time.monotonic() >= deadline:
                break
            time.sleep(self._poll_interval)
        return False

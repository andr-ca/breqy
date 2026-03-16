from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.event_log import EventLog
from system.orchestrator.router import Router
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState

if TYPE_CHECKING:
    from system.orchestrator.branch_manager import BranchManager
    from system.orchestrator.ci_adapter import CIAdapter
    from system.orchestrator.github_adapter import GitHubAdapter
    from system.orchestrator.session_manager import SessionManager


class OrchestratorLoop:
    def __init__(
        self,
        config: OrchestratorConfig,
        state_machine: ConcreteStateMachine,
        artifact_store: ArtifactStore,
        event_log: EventLog,
        event_queue: queue.Queue,
        *,
        branch_manager: BranchManager | None = None,
        github_adapter: GitHubAdapter | None = None,
        ci_adapter: CIAdapter | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._config = config
        self._sm = state_machine
        self._artifact_store = artifact_store
        self._log = event_log
        self._queue = event_queue
        self._stop_event = threading.Event()
        self._router = Router(config=config)
        self._branch_manager = branch_manager
        self._gh = github_adapter
        self._ci = ci_adapter
        self._session_manager = session_manager
        self._current_runner: AgentRunner | None = None
        self._retry_after: dict[str, float] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def force_kill_current(self) -> None:
        """Force-terminate any in-flight runner subprocess."""
        import subprocess as _sp
        runner = self._current_runner
        if runner and runner.proc and runner.proc.poll() is None:
            runner.proc.terminate()
            try:
                runner.proc.wait(timeout=5)
            except _sp.TimeoutExpired:
                runner.proc.kill()

    def flush(self, config: OrchestratorConfig) -> None:
        """Flush event log and write runtime-state.yaml."""
        import datetime

        import yaml as _yaml
        state_path = Path(config.orchestrator.runtime_state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(_yaml.dump({
            "shutdown_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "note": "graceful shutdown",
        }))

    def check_dependency_gate(
        self,
        task: Task,
        all_tasks: dict[str, tuple[Task, TaskEnvelope]],
    ) -> bool:
        """Return True if all dependencies are in DONE state."""
        env = all_tasks.get(task.task_id)
        if env is None:
            return True
        _, task_env = env
        for dep_id in task_env.dependencies:
            dep = all_tasks.get(dep_id)
            if dep is None or dep[0].state != TaskState.DONE:
                return False
        return True

    def check_merge_readiness(self, task: Task, branch: str) -> bool:
        """Return True iff merge-readiness artifact exists with verdict=pass."""
        artifact = self._artifact_store.read(
            task.task_id, "merge-readiness", MergeReadinessArtifact
        )
        return artifact is not None and artifact.verdict == "pass"

    def _emit(self, event: OrchestratorEvent) -> None:
        self._log.append(event)
        self._queue.put_nowait(event)

    def run(
        self,
        tasks: list[tuple[Task, TaskEnvelope]],
    ) -> None:
        """Main loop — processes tasks until stop() is called."""
        all_tasks = {t.task_id: (t, env) for t, env in tasks}
        while not self._stop_event.is_set():
            for task_id, (task, env) in list(all_tasks.items()):
                task = self._tick(task, env, all_tasks)
                all_tasks[task_id] = (task, env)
            self._stop_event.wait(timeout=self._config.orchestrator.poll_interval_seconds)

    def _tick(
        self,
        task: Task,
        env: TaskEnvelope,
        all_tasks: dict[str, tuple[Task, TaskEnvelope]],
    ) -> Task:
        """Single tick for one task. Returns updated task."""
        if task.state in (TaskState.DONE, TaskState.BLOCKED):
            return task

        if task.state == TaskState.NEW:
            if self.check_dependency_gate(task, all_tasks):
                task = self._sm.transition(task, TaskState.READY_FOR_SHAPING)
                self._emit(OrchestratorEvent(
                    task_id=task.task_id, event_type="state_transition",
                    from_state="NEW", to_state="READY_FOR_SHAPING",
                ))
            else:
                self._emit(OrchestratorEvent(
                    task_id=task.task_id, event_type="dependency_wait",
                    notes="Waiting for dependencies",
                ))
        return task

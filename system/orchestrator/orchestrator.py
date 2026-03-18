# system/orchestrator/orchestrator.py
from __future__ import annotations
import queue
import threading
import time
from pathlib import Path
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.branch_manager import BranchManager
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.event_log import EventLog
from system.orchestrator.github_adapter import GitHubAdapter
from system.orchestrator.router import Router
from system.orchestrator.agent_adapters.base import TaskContext
from system.orchestrator.schemas.artifacts import MergeReadinessArtifact, ParsedOutput
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState
from system.orchestrator.task_loader import TaskLoader


class OrchestratorLoop:
    def __init__(
        self,
        config: OrchestratorConfig,
        state_machine: ConcreteStateMachine,
        artifact_store: ArtifactStore,
        event_log: EventLog,
        event_queue: queue.Queue,
        credential_store: CredentialStore | None = None,
        loader: TaskLoader | None = None,
        branch_manager: BranchManager | None = None,
        ci_adapter: CIAdapter | None = None,
        github_adapter: GitHubAdapter | None = None,
    ) -> None:
        self._config = config
        self._sm = state_machine
        self._artifact_store = artifact_store
        self._log = event_log
        self._queue = event_queue
        self._stop_event = threading.Event()
        self._router = Router(config=config, credential_store=credential_store)
        self._current_process = None   # set by runner layer
        self._loader = loader
        self._branch_manager = branch_manager
        self._ci_adapter = ci_adapter
        self._github_adapter = github_adapter
        self._current_task_id: str | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def force_kill_current(self) -> None:
        """Force-terminate any in-flight runner subprocess."""
        import subprocess as _sp
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()
            try:
                self._current_process.wait(timeout=5)
            except _sp.TimeoutExpired:
                self._current_process.kill()

    def flush(self, config: OrchestratorConfig) -> None:
        """Flush event log and write runtime-state.yaml."""
        import yaml as _yaml
        import datetime
        state_path = Path(config.orchestrator.runtime_state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(_yaml.dump({
            "shutdown_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        """Returns True iff merge-readiness artifact exists with verdict=pass."""
        artifact = self._artifact_store.read(task.task_id, "merge-readiness", MergeReadinessArtifact)
        return artifact is not None and artifact.verdict == "pass"

    def _run_agent(
        self,
        task: Task,
        env: TaskEnvelope,
        role: str,
        prior_artifacts: dict[str, str] | None = None,
    ) -> ParsedOutput:
        runner, adapter = self._router.resolve(env.task_type, env.component, role)
        prior = dict(prior_artifacts) if prior_artifacts else {}
        failure_notes = prior.pop("failure_notes", "")
        context = TaskContext(
            task=env,
            prior_artifacts=prior,
            rework_count=task.rework_count,
            failure_notes=failure_notes,
        )
        prompt = adapter.build_prompt(env, context)
        run_context = RunContext(
            task_id=task.task_id,
            role=role,
            work_dir=Path.cwd(),
            session_id=task.session_id,
        )
        self._emit(OrchestratorEvent(
            task_id=task.task_id,
            event_type="agent_spawn",
            role=role,
            agent_type=type(runner).__name__,
        ))
        try:
            proc = runner.start(prompt, run_context)
            self._current_process = proc
            self._current_task_id = task.task_id
            stdout, _ = proc.communicate()
            result = RunResult(
                status="completed" if proc.returncode == 0 else "failed",
                output=stdout,
                exit_code=proc.returncode,
            )
        finally:
            self._current_process = None
            self._current_task_id = None
        output = adapter.parse_output(result)
        self._artifact_store.write(task.task_id, role, output)
        self._emit(OrchestratorEvent(
            task_id=task.task_id,
            event_type="agent_complete",
            role=role,
            notes=output.notes,
        ))
        return output

    def _handle_ready_for_branch_prep(self, task: Task, env: TaskEnvelope) -> Task:
        if self._branch_manager is None:
            return self._sm.force_block(task, notes="branch_manager not configured")
        try:
            slug = self._branch_manager.make_slug(env.title)
            branch = self._branch_manager.create_branch(task.task_id, env.task_type, slug)
            self._branch_manager.push(branch)
        except Exception as exc:
            return self._sm.force_block(task, notes=f"branch creation failed: {exc}")
        task = task.model_copy(update={"branch": branch})
        task = self._sm.transition(task, TaskState.READY_FOR_TEST_CASE_DESIGN)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_BRANCH_PREP", to_state="READY_FOR_TEST_CASE_DESIGN",
        ))
        return task

    def _handle_doer_in_progress(self, task: Task, env: TaskEnvelope) -> Task:
        """Orchestrator restart mid-run — treat as crash, route to retry."""
        task = self._sm.transition(task, TaskState.RETRY_PENDING)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
            notes="crash recovery: orchestrator restarted mid-run",
        ))
        return task

    def _handle_retry_pending(self, task: Task, env: TaskEnvelope) -> Task:
        if self._sm.can_transition(task, TaskState.DOER_IN_PROGRESS):
            task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="RETRY_PENDING", to_state="DOER_IN_PROGRESS",
            ))
        else:
            task = self._sm.transition(task, TaskState.BLOCKED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="RETRY_PENDING", to_state="BLOCKED",
                notes="retry limit reached",
            ))
        return task

    def _handle_check_failed(self, task: Task, env: TaskEnvelope) -> Task:
        if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
            task = self._sm.transition(task, TaskState.READY_FOR_DOER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="CHECK_FAILED", to_state="READY_FOR_DOER",
            ))
        else:
            task = self._sm.transition(task, TaskState.BLOCKED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="CHECK_FAILED", to_state="BLOCKED",
                notes="rework limit reached",
            ))
        return task

    def _handle_test_failed(self, task: Task, env: TaskEnvelope) -> Task:
        if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
            task = self._sm.transition(task, TaskState.READY_FOR_DOER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="TEST_FAILED", to_state="READY_FOR_DOER",
            ))
        else:
            task = self._sm.transition(task, TaskState.BLOCKED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="TEST_FAILED", to_state="BLOCKED",
                notes="rework limit reached",
            ))
        return task

    def _handle_qa_failed(self, task: Task, env: TaskEnvelope) -> Task:
        qa_out = self._artifact_store.read(task.task_id, "qa_automation", ParsedOutput)
        if qa_out is not None:
            task = task.model_copy(update={"failure_source": qa_out.failure_source})
        if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
            task = self._sm.transition(task, TaskState.READY_FOR_DOER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="QA_FAILED", to_state="READY_FOR_DOER",
            ))
        elif self._sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION):
            task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="QA_FAILED", to_state="READY_FOR_QA_AUTOMATION",
            ))
        else:
            task = self._sm.transition(task, TaskState.BLOCKED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="QA_FAILED", to_state="BLOCKED",
                notes=f"failure_source={task.failure_source}",
            ))
        return task

    def _emit(self, event: OrchestratorEvent) -> None:
        self._log.append(event)
        self._queue.put_nowait(event)

    def _cancel_task(self, task: Task, env: TaskEnvelope) -> None:
        """Kill running process, delete git branch, emit task_cancelled event."""
        if self._current_task_id == task.task_id:
            self.force_kill_current()
            self._current_process = None
            self._current_task_id = None
        if task.branch and self._branch_manager is not None:
            self._branch_manager.delete_branch(task.branch)
        self._emit(OrchestratorEvent(
            task_id=task.task_id,
            event_type="task_cancelled",
            from_state=task.state.value,
        ))

    def _sync_tasks(self, all_tasks: dict[str, tuple[Task, TaskEnvelope]]) -> None:
        """Diff loader results against all_tasks: insert new, cancel removed."""
        if self._loader is None:
            return
        fresh = {env.task_id: env for env in self._loader.load_pending()}
        for task_id, env in fresh.items():
            if task_id not in all_tasks:
                all_tasks[task_id] = (Task(task_id=task_id, state=TaskState.NEW), env)
        to_cancel = [
            (task, env)
            for task_id, (task, env) in list(all_tasks.items())
            if task_id not in fresh and task.state not in (TaskState.DONE, TaskState.BLOCKED)
        ]
        for task, env in to_cancel:
            self._cancel_task(task, env)
            del all_tasks[task.task_id]

    def run(self) -> None:
        """Main loop — polls for tasks and processes them until stop() is called."""
        all_tasks: dict[str, tuple[Task, TaskEnvelope]] = {}
        while not self._stop_event.is_set():
            self._sync_tasks(all_tasks)
            for task_id, (task, env) in list(all_tasks.items()):
                task = self._tick(task, env, all_tasks)
                all_tasks[task_id] = (task, env)
            time.sleep(self._config.orchestrator.poll_interval_seconds)

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

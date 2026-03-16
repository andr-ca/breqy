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
from system.orchestrator.schemas.artifacts import MergeReadinessArtifact, ParsedOutput
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState

from system.orchestrator.branch_manager import BranchManager

if TYPE_CHECKING:
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

    def _role_configured(self, task_type: str, component: str, role: str) -> bool:
        """Return True if role has a runner configured in routing_rules or agent_defaults."""
        specific = (
            self._config.routing_rules
            .get(task_type, {})
            .get(component, {})
            .get(role)
        )
        default = self._config.agent_defaults.get(role)
        return bool(specific or default)

    def _run_role(self, task: Task, env: TaskEnvelope, role: str) -> ParsedOutput:
        """Resolve runner+adapter, build prompt, run, parse and return output."""
        from pathlib import Path as _Path

        from system.orchestrator.agent_adapters.base import TaskContext
        from system.orchestrator.schemas.run_result import RunContext

        runner, adapter = self._router.resolve(env.task_type, env.component, role)
        prior: dict[str, str] = {}
        task_dir = _Path(self._config.orchestrator.artifact_base) / task.task_id
        if task_dir.exists():
            for p in task_dir.iterdir():
                prior[p.stem] = str(p)
        ctx = TaskContext(task=env, prior_artifacts=prior, rework_count=task.rework_count)
        prompt = adapter.build_prompt(env, ctx)
        run_ctx = RunContext(
            task_id=task.task_id, role=role, work_dir=_Path("."), session_id=task.session_id,
        )
        self._current_runner = runner
        try:
            result = runner.run(prompt, run_ctx)
        finally:
            self._current_runner = None
        return adapter.parse_output(result)

    def _persist_state(self, all_tasks: dict[str, tuple[Task, TaskEnvelope]]) -> None:
        """Write runtime-state.yaml with per-task state and counts."""
        import datetime

        import yaml as _yaml
        from pathlib import Path as _Path

        state_path = _Path(self._config.orchestrator.runtime_state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tasks_data = {
            tid: {
                "state": str(t.state),
                "rework_count": t.rework_count,
                "retry_count": t.retry_count,
                "session_id": t.session_id,
                "branch": t.branch,
                "pr_url": t.pr_url,
                "github_issue_number": t.github_issue_number,
                "failure_source": t.failure_source,
            }
            for tid, (t, _) in all_tasks.items()
        }
        state_path.write_text(_yaml.dump({
            "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "tasks": tasks_data,
        }))

    def _sync_github_label(self, task: Task, old_state: str) -> None:
        """Sync the GitHub Issue state label if GitHub adapter is configured."""
        if self._gh and task.github_issue_number:
            try:
                self._gh.set_task_state(
                    task.github_issue_number,
                    new_state=task.state,
                    old_state=old_state,
                )
            except Exception as exc:  # noqa: BLE001
                self._emit(OrchestratorEvent(
                    task_id=task.task_id, event_type="error",
                    notes=f"GitHub label sync failed: {exc}",
                ))

    def _do_transition(self, task: Task, to: TaskState) -> Task:
        """Transition + emit state_transition event + sync GitHub label."""
        old_state = str(task.state)
        task = self._sm.transition(task, to)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state=old_state, to_state=str(to),
        ))
        self._sync_github_label(task, old_state=old_state)
        return task

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
                task = self._do_transition(task, TaskState.READY_FOR_SHAPING)
            else:
                self._emit(OrchestratorEvent(
                    task_id=task.task_id, event_type="dependency_wait",
                    notes="Waiting for dependencies",
                ))
            return task

        if task.state == TaskState.READY_FOR_SHAPING:
            if not self._role_configured(env.task_type, env.component, "planner"):
                task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
                self._emit(OrchestratorEvent(
                    task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP",
                    notes="planner role not configured — shaping skipped",
                ))
            else:
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="planner"))
                try:
                    parsed = self._run_role(task, env, "planner")
                except Exception as exc:  # noqa: BLE001
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes=f"planner raised exception: {exc}"))
                    return task
                if parsed.status == "pass":
                    task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                        from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP"))
                else:
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes=f"planner returned fail: {parsed.notes}"))
            return task

        if task.state == TaskState.READY_FOR_BRANCH_PREP:
            if not self._branch_manager:
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes="branch_manager not injected"))
                return task
            bm = self._branch_manager
            slug = BranchManager.make_slug(env.title)
            if task.branch and bm.branch_exists(task.branch):
                branch = task.branch
            else:
                try:
                    branch = bm.create_branch(env.task_id, env.task_type, slug)
                except Exception as exc:  # noqa: BLE001
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes=f"create_branch failed: {exc}"))
                    return task
            if bm.is_stale(branch, self._config.orchestrator.branch_stale_days):
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="stale_warning",
                    notes=f"branch {branch} is stale; rebasing onto {bm.merge_target(env.task_type)}"))
                try:
                    bm.rebase(branch, bm.merge_target(env.task_type))
                except Exception as exc:  # noqa: BLE001
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes=f"rebase failed: {exc}"))
                    return task
            task = task.model_copy(update={"branch": branch})
            task = self._sm.transition(task, TaskState.READY_FOR_TEST_CASE_DESIGN)
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_BRANCH_PREP", to_state="READY_FOR_TEST_CASE_DESIGN"))
            return task

        if task.state == TaskState.READY_FOR_TEST_CASE_DESIGN:
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="tester"))
            try:
                parsed = self._run_role(task, env, "tester")
            except Exception as exc:  # noqa: BLE001
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"tester (test-cases) failed: {exc}"))
                return task
            if parsed.status == "pass":
                task = self._sm.transition(task, TaskState.READY_FOR_DOER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_TEST_CASE_DESIGN", to_state="READY_FOR_DOER"))
            else:
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"tester returned fail: {parsed.notes}"))
            return task

        def _do_run_doer(task: Task) -> Task:
            """Run doer subprocess and advance task state. Closes over self and env."""
            import time as _time
            # Transition to DOER_IN_PROGRESS if coming from READY_FOR_DOER
            if task.state == TaskState.READY_FOR_DOER:
                prior_state = str(task.state)
                task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state=prior_state, to_state="DOER_IN_PROGRESS"))
            try:
                parsed = self._run_role(task, env, "doer")
                err_notes = parsed.notes
            except Exception as exc:  # noqa: BLE001
                parsed = None
                err_notes = str(exc)
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_complete",
                role="doer", notes=err_notes))
            if parsed and parsed.status == "pass":
                if parsed.session_id:
                    task = task.model_copy(update={"session_id": parsed.session_id})
                task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER"))
            elif parsed and "rate_limited" in parsed.notes:
                if self._sm.can_transition(task, TaskState.BLOCKED):
                    # retry_count >= max_retries → exhausted
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes="max retries exceeded"))
                else:
                    task = self._sm.transition(task, TaskState.RETRY_PENDING)
                    self._retry_after[task.task_id] = (
                        _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
                    )
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="retry_pending",
                        notes=f"rate limited; retry after {self._config.orchestrator.retry_backoff_seconds}s"))
            else:
                if self._sm.can_transition(task, TaskState.BLOCKED):
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes=f"doer failed and retries exhausted: {err_notes}"))
                else:
                    task = self._sm.transition(task, TaskState.RETRY_PENDING)
                    self._retry_after[task.task_id] = (
                        _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
                    )
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="retry_pending",
                        notes=f"doer failed; retry pending: {err_notes}"))
            return task

        if task.state == TaskState.READY_FOR_DOER:
            return _do_run_doer(task)

        if task.state == TaskState.DOER_IN_PROGRESS:
            if not self._artifact_store.exists(task.task_id, "doer-report"):
                return _do_run_doer(task)
            task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER",
                notes="restart recovery: doer-report found"))
            return task

        if task.state == TaskState.READY_FOR_CHECKER:
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="checker"))
            try:
                parsed = self._run_role(task, env, "checker")
            except Exception as exc:  # noqa: BLE001
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"checker exception: {exc}"))
                return task
            if parsed.status == "pass":
                task = self._sm.transition(task, TaskState.READY_FOR_TESTER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_CHECKER", to_state="READY_FOR_TESTER"))
            else:
                task = self._sm.transition(task, TaskState.CHECK_FAILED)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_CHECKER", to_state="CHECK_FAILED", notes=parsed.notes))
            return task

        if task.state == TaskState.CHECK_FAILED:
            if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
                task = self._sm.transition(task, TaskState.READY_FOR_DOER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
                    from_state="CHECK_FAILED", to_state="READY_FOR_DOER",
                    notes=f"rework {task.rework_count}"))
            else:
                task = self._sm.transition(task, TaskState.BLOCKED)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes="max rework loops exceeded (checker)"))
            return task

        if task.state == TaskState.RETRY_PENDING:
            import time as _time
            retry_after = self._retry_after.get(task.task_id, 0.0)
            if _time.monotonic() < retry_after:
                return task  # backoff not elapsed
            # Re-run doer from RETRY_PENDING
            # First advance to DOER_IN_PROGRESS (incrementing retry_count via state machine)
            task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                from_state="RETRY_PENDING", to_state="DOER_IN_PROGRESS"))
            try:
                parsed = self._run_role(task, env, "doer")
                err_notes = parsed.notes
            except Exception as exc:  # noqa: BLE001
                parsed = None
                err_notes = str(exc)
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_complete",
                role="doer", notes=err_notes))
            if parsed and parsed.status == "pass":
                if parsed.session_id:
                    task = task.model_copy(update={"session_id": parsed.session_id})
                task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER"))
            elif parsed and "rate_limited" in parsed.notes:
                if self._sm.can_transition(task, TaskState.BLOCKED):
                    task = self._sm.force_block(task)
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                        notes="rate limit retries exhausted"))
                else:
                    task = self._sm.transition(task, TaskState.RETRY_PENDING)
                    self._retry_after[task.task_id] = (
                        _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
                    )
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="retry_pending",
                        notes="rate limited again"))
            else:
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"doer failed on retry: {err_notes}"))
            return task

        if task.state == TaskState.READY_FOR_TESTER:
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="tester"))
            try:
                parsed = self._run_role(task, env, "tester")
            except Exception as exc:  # noqa: BLE001
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"tester exception: {exc}"))
                return task
            if parsed.status == "pass":
                task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_TESTER", to_state="READY_FOR_QA_AUTOMATION"))
            else:
                task = self._sm.transition(task, TaskState.TEST_FAILED)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_TESTER", to_state="TEST_FAILED", notes=parsed.notes))
            return task

        if task.state == TaskState.TEST_FAILED:
            if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
                task = self._sm.transition(task, TaskState.READY_FOR_DOER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
                    from_state="TEST_FAILED", to_state="READY_FOR_DOER",
                    notes=f"rework {task.rework_count}"))
            else:
                task = self._sm.transition(task, TaskState.BLOCKED)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes="max rework loops exceeded (tester)"))
            return task

        if task.state == TaskState.READY_FOR_QA_AUTOMATION:
            if not self._role_configured(env.task_type, env.component, "qa_automation"):
                task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW",
                    notes="qa_automation role not configured — skipped"))
                return task
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn",
                role="qa_automation"))
            try:
                parsed = self._run_role(task, env, "qa_automation")
            except Exception as exc:  # noqa: BLE001
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"qa_automation exception: {exc}"))
                return task
            if parsed.status == "pass":
                task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW"))
            else:
                failure_source = parsed.failure_source or "broken_implementation"
                task = task.model_copy(update={"failure_source": failure_source})
                task = self._sm.transition(task, TaskState.QA_FAILED)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                    from_state="READY_FOR_QA_AUTOMATION", to_state="QA_FAILED",
                    notes=f"failure_source={failure_source}"))
            return task

        if task.state == TaskState.QA_FAILED:
            if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
                task = self._sm.transition(task, TaskState.READY_FOR_DOER)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
                    from_state="QA_FAILED", to_state="READY_FOR_DOER",
                    notes=f"rework {task.rework_count}"))
            elif self._sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION):
                task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
                    from_state="QA_FAILED", to_state="READY_FOR_QA_AUTOMATION",
                    notes=f"rework {task.rework_count}"))
            else:
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"QA_FAILED blocked: failure_source={task.failure_source}"))
            return task

        if task.state == TaskState.READY_FOR_MERGE_REVIEW:
            branch = task.branch or ""
            ci_green = False
            if self._ci:
                ci_green = self._ci.wait_for_green(
                    branch, timeout_minutes=self._config.github.ci_timeout_minutes
                )
            else:
                ci_green = self.check_merge_readiness(task, branch)

            if not ci_green:
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="ci_result",
                    notes=f"CI not green for {branch}; staying in READY_FOR_MERGE_REVIEW"))
                return task

            import datetime as _dt
            required = ["task-envelope", "doer-report", "checker-report",
                        "deterministic-test-report", "qa-automation-report", "lessons"]
            present = [n for n in required if self._artifact_store.exists(task.task_id, n)]
            merge_target = (
                self._branch_manager.merge_target(env.task_type)
                if self._branch_manager else "dev"
            )
            branch_is_current = (
                not self._branch_manager or
                not self._branch_manager.is_stale(branch, self._config.orchestrator.branch_stale_days)
            )
            artifact = MergeReadinessArtifact(
                task_id=task.task_id,
                checked_at=_dt.datetime.now(_dt.UTC).isoformat(),
                artifacts_present=present,
                branch=branch,
                merge_target=merge_target,
                ci_conclusion="success",
                branch_is_current=branch_is_current,
                verdict="pass",
            )
            self._artifact_store.write(task.task_id, "merge-readiness", artifact)
            task = self._do_transition(task, TaskState.READY_FOR_LESSONS)
            return task

        if task.state == TaskState.READY_FOR_LESSONS:
            self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="lessons"))
            try:
                self._run_role(task, env, "lessons")
            except Exception as exc:  # noqa: BLE001
                task = self._sm.force_block(task)
                self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                    notes=f"lessons exception: {exc}"))
                return task
            task = self._do_transition(task, TaskState.READY_FOR_HUMAN_REVIEW)
            return task

        if task.state == TaskState.READY_FOR_HUMAN_REVIEW:
            if not self._gh:
                return task
            if not task.pr_url and task.branch:
                try:
                    pr_url = self._gh.create_pr(
                        branch=task.branch,
                        title=f"{env.task_id}: {env.title}",
                        body=(
                            f"Automated PR for task {env.task_id}.\n\nAcceptance criteria:\n" +
                            "\n".join(f"- {c}" for c in env.acceptance_criteria)
                        ),
                    )
                    task = task.model_copy(update={"pr_url": pr_url})
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="artifact_written",
                        notes=f"PR created: {pr_url}"))
                except Exception as exc:  # noqa: BLE001
                    self._emit(OrchestratorEvent(task_id=task.task_id, event_type="error",
                        notes=f"create_pr failed: {exc}"))
                    return task
            if task.pr_url and self._gh.pr_is_merged(task.pr_url):
                task = self._do_transition(task, TaskState.DONE)
            return task

        return task

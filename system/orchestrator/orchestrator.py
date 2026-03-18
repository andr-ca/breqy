# system/orchestrator/orchestrator.py
from __future__ import annotations
import datetime
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


_HANDLERS: dict[TaskState, str] = {
    TaskState.READY_FOR_SHAPING:           "_handle_ready_for_shaping",
    TaskState.READY_FOR_BRANCH_PREP:       "_handle_ready_for_branch_prep",
    TaskState.READY_FOR_TEST_CASE_DESIGN:  "_handle_ready_for_test_case_design",
    TaskState.READY_FOR_DOER:              "_handle_ready_for_doer",
    TaskState.DOER_IN_PROGRESS:            "_handle_doer_in_progress",
    TaskState.READY_FOR_CHECKER:           "_handle_ready_for_checker",
    TaskState.CHECK_FAILED:                "_handle_check_failed",
    TaskState.READY_FOR_TESTER:            "_handle_ready_for_tester",
    TaskState.TEST_FAILED:                 "_handle_test_failed",
    TaskState.READY_FOR_QA_AUTOMATION:     "_handle_ready_for_qa",
    TaskState.QA_FAILED:                   "_handle_qa_failed",
    TaskState.READY_FOR_MERGE_REVIEW:      "_handle_ready_for_merge_review",
    TaskState.READY_FOR_LESSONS:           "_handle_ready_for_lessons",
    TaskState.READY_FOR_HUMAN_REVIEW:      "_handle_ready_for_human_review",
    TaskState.RETRY_PENDING:               "_handle_retry_pending",
}


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
        # NOTE: We call runner.start() (not runner.run()) to obtain the Popen handle for
        # _cancel_task(). This bypasses ClaudeRunner.run()'s rate-limit detection — the
        # adapter's parse_output() is responsible for handling rate-limit signals instead.
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

    def _handle_ready_for_shaping(self, task: Task, env: TaskEnvelope) -> Task:
        output = self._run_agent(task, env, "planner")
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP",
            ))
        else:
            task = self._sm.force_block(task, notes="planner failed")
        return task

    def _handle_ready_for_test_case_design(self, task: Task, env: TaskEnvelope) -> Task:
        output = self._run_agent(task, env, "tester")
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_DOER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_TEST_CASE_DESIGN", to_state="READY_FOR_DOER",
            ))
        else:
            task = self._sm.force_block(task, notes="test-case design failed")
        return task

    def _handle_ready_for_doer(self, task: Task, env: TaskEnvelope) -> Task:
        task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_DOER", to_state="DOER_IN_PROGRESS",
        ))
        try:
            output = self._run_agent(task, env, "doer")
        except Exception:
            task = self._sm.transition(task, TaskState.RETRY_PENDING)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
                notes="runner exception",
            ))
            return task
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER",
            ))
        else:
            task = self._sm.transition(task, TaskState.RETRY_PENDING)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
            ))
        return task

    def _handle_ready_for_checker(self, task: Task, env: TaskEnvelope) -> Task:
        base = self._branch_manager.merge_target(env.task_type) if self._branch_manager else "dev"
        diff = self._branch_manager.diff(task.branch or "", base) if self._branch_manager else ""
        doer_out = self._artifact_store.read(task.task_id, "doer", ParsedOutput)
        doer_notes = doer_out.notes if doer_out else ""
        prior = {
            "git_diff": diff,
            "doer_report": doer_notes,
            "failure_notes": doer_notes if task.rework_count > 0 else "",
        }
        output = self._run_agent(task, env, "checker", prior_artifacts=prior)
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_TESTER)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_CHECKER", to_state="READY_FOR_TESTER",
            ))
        else:
            task = self._sm.transition(task, TaskState.CHECK_FAILED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_CHECKER", to_state="CHECK_FAILED",
            ))
        return task

    def _handle_ready_for_tester(self, task: Task, env: TaskEnvelope) -> Task:
        output = self._run_agent(task, env, "tester")
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_TESTER", to_state="READY_FOR_QA_AUTOMATION",
            ))
        else:
            task = self._sm.transition(task, TaskState.TEST_FAILED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_TESTER", to_state="TEST_FAILED",
            ))
        return task

    def _handle_ready_for_qa(self, task: Task, env: TaskEnvelope) -> Task:
        output = self._run_agent(task, env, "qa_automation")
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW",
            ))
        else:
            task = self._sm.transition(task, TaskState.QA_FAILED)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_QA_AUTOMATION", to_state="QA_FAILED",
            ))
        return task

    def _handle_ready_for_merge_review(self, task: Task, env: TaskEnvelope) -> Task:
        base = self._branch_manager.merge_target(env.task_type) if self._branch_manager else "dev"
        # Create PR if not yet created
        if task.pr_url is None:
            if self._github_adapter is None:
                return self._sm.force_block(task, notes="github_adapter not configured")
            pr_url = self._github_adapter.create_pr(
                branch=task.branch or "",
                base=base,
                title=f"{env.task_id}: {env.title}",
                body=f"Automated PR for task {env.task_id}.",
            )
            task = task.model_copy(update={"pr_url": pr_url})

        # Non-blocking CI poll
        if self._ci_adapter is None:
            return self._sm.force_block(task, notes="ci_adapter not configured")
        run = self._ci_adapter.get_latest_run(task.branch or "")
        if run is None or run.status != "completed":
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="ci_poll",
                notes=f"CI not complete yet for {task.branch}",
            ))
            return task  # stay in READY_FOR_MERGE_REVIEW

        if run.conclusion != "success":
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="ci_result",
                notes=f"CI failed: conclusion={run.conclusion}",
            ))
            return self._sm.force_block(task, notes=f"CI failed: {run.conclusion}")

        # CI green — use base computed above (no second merge_target call)
        artifact = MergeReadinessArtifact(
            task_id=task.task_id,
            checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            artifacts_present=[],
            branch=task.branch or "",
            merge_target=base,
            ci_conclusion=run.conclusion,
            branch_is_current=True,
            verdict="pass",
        )
        self._artifact_store.write(task.task_id, "merge-readiness", artifact)
        task = self._sm.transition(task, TaskState.READY_FOR_LESSONS)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_MERGE_REVIEW", to_state="READY_FOR_LESSONS",
        ))
        return task

    def _handle_ready_for_lessons(self, task: Task, env: TaskEnvelope) -> Task:
        output = self._run_agent(task, env, "lessons")
        if output.status == "pass":
            task = self._sm.transition(task, TaskState.READY_FOR_HUMAN_REVIEW)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="READY_FOR_LESSONS", to_state="READY_FOR_HUMAN_REVIEW",
            ))
        else:
            task = self._sm.force_block(task, notes="lessons agent failed")
        return task

    def _handle_ready_for_human_review(self, task: Task, env: TaskEnvelope) -> Task:
        if self._github_adapter is None:
            return self._sm.force_block(task, notes="github_adapter not configured")
        if task.pr_url is None:
            return self._sm.force_block(task, notes="pr_url not set — cannot merge")
        self._github_adapter.merge_pr(task.pr_url)
        task = self._sm.transition(task, TaskState.DONE)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_HUMAN_REVIEW", to_state="DONE",
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

        handler_name = _HANDLERS.get(task.state)
        if handler_name is None:
            return task
        return getattr(self, handler_name)(task, env)

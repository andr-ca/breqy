import queue
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import Task, TaskState, ConcreteStateMachine
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.github_adapter import GitHubAdapter


def _make_loop(tmp_path, ci_adapter=None, github_adapter=None, branch_manager=None):
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude", "checker": "codex"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()
    return OrchestratorLoop(
        config=cfg, state_machine=sm, artifact_store=store,
        event_log=log, event_queue=eq,
        ci_adapter=ci_adapter,
        github_adapter=github_adapter,
        branch_manager=branch_manager,
    )


@pytest.fixture
def task_env():
    return TaskEnvelope(task_id="BRQ-1", title="Test", task_type="feature", component="backend")


@pytest.fixture
def loop(tmp_path):
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    event_queue: queue.Queue = queue.Queue()
    return OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log,
        event_queue=event_queue,
    )


def test_loop_advances_new_task_with_no_deps(loop):
    # Task envelope present, dependencies list is empty → gate passes
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature",
                       component="backend", dependencies=[])
    result = loop.check_dependency_gate(task, all_tasks={"BRQ-1": (task, env)})
    assert result is True


def test_loop_holds_task_with_unmet_deps(loop):
    task = Task(task_id="BRQ-2", state=TaskState.NEW)
    dep_task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env_brq1 = TaskEnvelope(task_id="BRQ-1", title="dep", task_type="feature", component="backend")
    env_brq2 = TaskEnvelope(task_id="BRQ-2", title="t", task_type="feature",
                             component="backend", dependencies=["BRQ-1"])
    all_tasks = {
        "BRQ-1": (dep_task, env_brq1),
        "BRQ-2": (task, env_brq2),
    }
    result = loop.check_dependency_gate(task, all_tasks=all_tasks)
    assert result is False


def test_loop_dep_gate_passes_when_dep_done(loop):
    task = Task(task_id="BRQ-2", state=TaskState.NEW)
    dep_task = Task(task_id="BRQ-1", state=TaskState.DONE)
    env_brq1 = TaskEnvelope(task_id="BRQ-1", title="dep", task_type="feature", component="backend")
    env_brq2 = TaskEnvelope(task_id="BRQ-2", title="t", task_type="feature",
                             component="backend", dependencies=["BRQ-1"])
    all_tasks = {
        "BRQ-1": (dep_task, env_brq1),
        "BRQ-2": (task, env_brq2),
    }
    result = loop.check_dependency_gate(task, all_tasks=all_tasks)
    assert result is True


def test_merge_readiness_check_pass(loop, task_env, tmp_path):
    store = loop._artifact_store
    from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
    artifact = MergeReadinessArtifact(
        task_id="BRQ-1",
        checked_at="2026-03-14T14:00:00Z",
        artifacts_present=["task-envelope", "doer-report"],
        branch="feat/BRQ-1-test",
        merge_target="dev",
        ci_conclusion="success",
        branch_is_current=True,
        verdict="pass",
    )
    store.write("BRQ-1", "merge-readiness", artifact)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW)
    result = loop.check_merge_readiness(task, branch="feat/BRQ-1-test")
    assert result is True


def test_merge_readiness_check_missing(loop, task_env):
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW)
    result = loop.check_merge_readiness(task, branch="feat/BRQ-1-test")
    assert result is False


def test_cancel_task_emits_task_cancelled_event(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._cancel_task(task, env)
    event = loop._queue.get_nowait()
    assert event.event_type == "task_cancelled"
    assert event.task_id == "BRQ-1"
    assert event.from_state == "DOER_IN_PROGRESS"


def test_cancel_task_deletes_branch_when_set(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, branch="feat/BRQ-1-test")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_bm = MagicMock()
    loop._branch_manager = mock_bm
    loop._cancel_task(task, env)
    mock_bm.delete_branch.assert_called_once_with("feat/BRQ-1-test")


def test_cancel_task_skips_branch_deletion_when_no_branch(loop):
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_bm = MagicMock()
    loop._branch_manager = mock_bm
    loop._cancel_task(task, env)
    mock_bm.delete_branch.assert_not_called()


def test_cancel_task_kills_process_when_task_id_matches(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running
    loop._current_process = mock_proc
    loop._current_task_id = "BRQ-1"
    loop._cancel_task(task, env)
    mock_proc.terminate.assert_called_once()
    assert loop._current_process is None
    assert loop._current_task_id is None


def test_cancel_task_does_not_kill_process_when_task_id_differs(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    loop._current_process = mock_proc
    loop._current_task_id = "BRQ-2"
    loop._cancel_task(task, env)
    mock_proc.terminate.assert_not_called()
    assert loop._current_task_id == "BRQ-2"


def test_sync_tasks_adds_new_task(loop):
    all_tasks = {}
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = [env]
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert all_tasks["BRQ-1"][0].state == TaskState.NEW


def test_sync_tasks_does_not_overwrite_existing_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = [env]
    loop._sync_tasks(all_tasks)
    assert all_tasks["BRQ-1"][0].state == TaskState.READY_FOR_SHAPING


def test_sync_tasks_cancels_removed_non_terminal_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []  # task gone
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" not in all_tasks
    event = loop._queue.get_nowait()
    assert event.event_type == "task_cancelled"


def test_sync_tasks_does_not_cancel_done_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.DONE)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert loop._queue.empty()


def test_sync_tasks_does_not_cancel_blocked_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.BLOCKED)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert loop._queue.empty()


def test_sync_tasks_no_op_when_loader_is_none(loop):
    all_tasks = {}
    loop._loader = None
    loop._sync_tasks(all_tasks)  # must not raise
    assert all_tasks == {}


def test_run_calls_sync_tasks_each_tick(loop):
    call_count = [0]
    def fake_load():
        call_count[0] += 1
        loop._stop_event.set()  # stop after first call
        return []
    loop._loader = MagicMock()
    loop._loader.load_pending.side_effect = fake_load
    loop.run()
    assert call_count[0] == 1


def test_loop_stores_ci_adapter(tmp_path):
    mock_ci = MagicMock(spec=CIAdapter)
    loop = _make_loop(tmp_path, ci_adapter=mock_ci)
    assert loop._ci_adapter is mock_ci


def test_loop_stores_github_adapter(tmp_path):
    mock_gh = MagicMock(spec=GitHubAdapter)
    loop = _make_loop(tmp_path, github_adapter=mock_gh)
    assert loop._github_adapter is mock_gh


def test_loop_ci_adapter_defaults_to_none(tmp_path):
    loop = _make_loop(tmp_path)
    assert loop._ci_adapter is None


def test_loop_github_adapter_defaults_to_none(tmp_path):
    loop = _make_loop(tmp_path)
    assert loop._github_adapter is None


def test_run_agent_stores_artifact_and_emits_events(tmp_path):
    loop = _make_loop(tmp_path)

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": "done"}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[], notes="done")

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")

    output = loop._run_agent(task, env, "planner")

    assert output.status == "pass"
    # artifact written
    from system.orchestrator.schemas.artifacts import ParsedOutput as PO
    stored = loop._artifact_store.read("BRQ-1", "planner", PO)
    assert stored is not None
    assert stored.status == "pass"
    # events emitted
    events = []
    while not loop._queue.empty():
        events.append(loop._queue.get_nowait())
    event_types = [e.event_type for e in events]
    assert "agent_spawn" in event_types
    assert "agent_complete" in event_types


def test_run_agent_clears_process_tracking_after_run(tmp_path):
    loop = _make_loop(tmp_path)

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": ""}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[])

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._run_agent(task, env, "planner")

    assert loop._current_process is None
    assert loop._current_task_id is None


def test_run_agent_clears_tracking_on_exception(tmp_path):
    loop = _make_loop(tmp_path)

    mock_runner = MagicMock()
    mock_runner.start.side_effect = RuntimeError("spawn failed")
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")

    with pytest.raises(RuntimeError):
        loop._run_agent(task, env, "planner")

    assert loop._current_process is None
    assert loop._current_task_id is None


def test_run_agent_extracts_failure_notes_from_prior_artifacts(tmp_path):
    """failure_notes key is removed from prior_artifacts and placed in TaskContext.failure_notes."""
    loop = _make_loop(tmp_path)

    captured_context: list = []

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": ""}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()

    def capture_prompt(env, context):
        captured_context.append(context)
        return "prompt"

    mock_adapter.build_prompt.side_effect = capture_prompt
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[])

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    prior = {"failure_notes": "checker said X", "some_key": "some_val"}

    loop._run_agent(task, env, "doer", prior_artifacts=prior)

    ctx = captured_context[0]
    assert ctx.failure_notes == "checker said X"
    assert "failure_notes" not in ctx.prior_artifacts
    assert "some_key" in ctx.prior_artifacts


# --- _handle_ready_for_branch_prep ---

def test_handle_branch_prep_creates_and_pushes_branch(tmp_path):
    mock_bm = MagicMock()
    mock_bm.make_slug.return_value = "add-feature"
    mock_bm.create_branch.return_value = "feat/BRQ-1-add-feature"
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_branch_prep(task, env)
    mock_bm.create_branch.assert_called_once_with("BRQ-1", "feature", "add-feature")
    mock_bm.push.assert_called_once_with("feat/BRQ-1-add-feature")
    assert result.branch == "feat/BRQ-1-add-feature"
    assert result.state == TaskState.READY_FOR_TEST_CASE_DESIGN


def test_handle_branch_prep_blocks_on_exception(tmp_path):
    mock_bm = MagicMock()
    mock_bm.make_slug.return_value = "add-feature"
    mock_bm.create_branch.side_effect = Exception("git error")
    loop = _make_loop(tmp_path, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_branch_prep(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_branch_prep_blocks_when_branch_manager_is_none(tmp_path):
    loop = _make_loop(tmp_path)  # no branch_manager
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_branch_prep(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_doer_in_progress ---

def test_handle_doer_in_progress_transitions_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_doer_in_progress(task, env)
    assert result.state == TaskState.RETRY_PENDING


# --- _handle_retry_pending ---

def test_handle_retry_pending_retries_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_retry_pending(task, env)
    assert result.state == TaskState.DOER_IN_PROGRESS
    assert result.retry_count == 1


def test_handle_retry_pending_blocks_when_limit_reached(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_retry_pending(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_check_failed ---

def test_handle_check_failed_reworks_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_check_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 1


def test_handle_check_failed_blocks_at_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_check_failed(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_test_failed ---

def test_handle_test_failed_reworks_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=2)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_test_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 3


def test_handle_test_failed_blocks_at_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_test_failed(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_qa_failed ---

def test_handle_qa_failed_reworks_broken_implementation(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_implementation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER


def test_handle_qa_failed_reworks_broken_automation(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_automation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.READY_FOR_QA_AUTOMATION


def test_handle_qa_failed_blocks_on_ambiguous_criteria(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="ambiguous_criteria", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_qa_failed_blocks_at_rework_limit(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_implementation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.BLOCKED


# ---------------------------------------------------------------------------
# Helpers for agent-invoking handler tests
# ---------------------------------------------------------------------------

def _mock_run_agent_pass(loop):
    """Patch _run_agent to return a passing ParsedOutput."""
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._run_agent = MagicMock(
        return_value=ParsedOutput(status="pass", artifact_paths=[], notes="ok")
    )


def _mock_run_agent_fail(loop):
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._run_agent = MagicMock(
        return_value=ParsedOutput(status="fail", artifact_paths=[], notes="fail")
    )


# --- shaping ---

def test_handle_shaping_pass_advances_to_branch_prep(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_shaping(task, env)
    assert result.state == TaskState.READY_FOR_BRANCH_PREP
    loop._run_agent.assert_called_once_with(task, env, "planner")


def test_handle_shaping_fail_blocks(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_shaping(task, env)
    assert result.state == TaskState.BLOCKED


# --- test_case_design ---

def test_handle_test_case_design_pass_advances_to_doer(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TEST_CASE_DESIGN)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_test_case_design(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    loop._run_agent.assert_called_once_with(task, env, "tester")


# --- doer ---

def test_handle_doer_pass_advances_to_checker(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.READY_FOR_CHECKER


def test_handle_doer_fail_advances_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.RETRY_PENDING


def test_handle_doer_exception_advances_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    loop._run_agent = MagicMock(side_effect=RuntimeError("crash"))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.RETRY_PENDING


# --- checker ---

def test_handle_checker_pass_advances_to_tester(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    mock_bm = MagicMock()
    mock_bm.diff.return_value = "diff text"
    mock_bm.merge_target.return_value = "dev"
    loop._branch_manager = mock_bm
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "doer",
        ParsedOutput(status="pass", artifact_paths=[], notes="done"))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER, branch="feat/BRQ-1-t")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_checker(task, env)
    assert result.state == TaskState.READY_FOR_TESTER
    # verify prior_artifacts passed to _run_agent
    call_kwargs = loop._run_agent.call_args
    prior = call_kwargs[1]["prior_artifacts"] if call_kwargs[1] else call_kwargs[0][3]
    assert "git_diff" in prior
    assert prior["git_diff"] == "diff text"


def test_handle_checker_fail_advances_to_check_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    mock_bm = MagicMock()
    mock_bm.diff.return_value = ""
    mock_bm.merge_target.return_value = "dev"
    loop._branch_manager = mock_bm
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "doer",
        ParsedOutput(status="pass", artifact_paths=[], notes=""))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER, branch="feat/BRQ-1-t")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_checker(task, env)
    assert result.state == TaskState.CHECK_FAILED


# --- tester ---

def test_handle_tester_pass_advances_to_qa(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_tester(task, env)
    assert result.state == TaskState.READY_FOR_QA_AUTOMATION


def test_handle_tester_fail_advances_to_test_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_tester(task, env)
    assert result.state == TaskState.TEST_FAILED


# --- qa ---

def test_handle_qa_pass_advances_to_merge_review(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_qa(task, env)
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW


def test_handle_qa_fail_advances_to_qa_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_qa(task, env)
    assert result.state == TaskState.QA_FAILED


# --- lessons ---

def test_handle_lessons_pass_advances_to_human_review(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_LESSONS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_lessons(task, env)
    assert result.state == TaskState.READY_FOR_HUMAN_REVIEW


# --- _handle_ready_for_merge_review ---

from system.orchestrator.ci_adapter import CiRun


def test_handle_merge_review_creates_pr_if_not_set(tmp_path):
    mock_gh = MagicMock()
    mock_gh.create_pr.return_value = "https://github.com/owner/repo/pull/7"
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = None  # CI not started yet
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=mock_gh, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url=None)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    mock_gh.create_pr.assert_called_once()
    assert result.pr_url == "https://github.com/owner/repo/pull/7"
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW  # CI not done, stays


def test_handle_merge_review_does_not_recreate_pr(tmp_path):
    mock_gh = MagicMock()
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = None
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=mock_gh, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._handle_ready_for_merge_review(task, env)
    mock_gh.create_pr.assert_not_called()


def test_handle_merge_review_stays_when_ci_in_progress(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="in_progress", conclusion=None, branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW


def test_handle_merge_review_advances_on_ci_green(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="completed", conclusion="success", branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.READY_FOR_LESSONS
    # MergeReadinessArtifact written
    from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
    artifact = loop._artifact_store.read("BRQ-1", "merge-readiness", MergeReadinessArtifact)
    assert artifact is not None
    assert artifact.verdict == "pass"


def test_handle_merge_review_blocks_on_ci_failure(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="completed", conclusion="failure", branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_merge_review_blocks_when_ci_adapter_none(tmp_path):
    loop = _make_loop(tmp_path)  # no ci_adapter
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_merge_review_blocks_when_github_adapter_none_and_no_pr(tmp_path):
    loop = _make_loop(tmp_path)  # no github_adapter, no ci_adapter
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url=None)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.BLOCKED

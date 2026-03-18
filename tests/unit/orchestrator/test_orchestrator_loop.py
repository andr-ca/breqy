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

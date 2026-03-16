import queue
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.branch_manager import BranchManager
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.config import GitHubConfig, OrchestratorConfig, OrchestratorSettings
from system.orchestrator.event_log import EventLog
from system.orchestrator.github_adapter import GitHubAdapter
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.session_manager import SessionManager
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState


@pytest.fixture
def task_env():
    return TaskEnvelope(task_id="BRQ-1", title="Test", task_type="feature", component="backend")


@pytest.fixture
def loop(tmp_path):
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={
            "doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"
        },
    )
    sm = ConcreteStateMachine()
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


def test_loop_constructor_accepts_optional_deps(loop):
    # The fixture-constructed loop has None deps by default
    assert loop._branch_manager is None
    assert loop._gh is None
    assert loop._ci is None
    assert loop._session_manager is None


def test_loop_force_kill_uses_runner_proc(tmp_path):
    cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm, artifact_store=store,
        event_log=log, event_queue=queue.Queue(),
    )
    mock_runner = MagicMock()
    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.poll.return_value = None   # still running
    mock_runner.proc = mock_proc
    loop._current_runner = mock_runner
    loop.force_kill_current()
    mock_proc.terminate.assert_called_once()


def test_claude_runner_sets_proc_on_run(tmp_path):
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    from system.orchestrator.schemas.run_result import RunContext
    runner = ClaudeRunner()
    ctx = RunContext(task_id="t1", role="doer", work_dir=tmp_path)
    with patch("system.orchestrator.runners.claude_runner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc
        runner.run("prompt", ctx)
    assert runner.proc is mock_proc


def test_role_configured_with_agent_defaults(tmp_path):
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"planner": "claude"},
    )
    sm = ConcreteStateMachine()
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=ArtifactStore(base=tmp_path / "art"),
        event_log=EventLog(path=tmp_path / "events.jsonl"),
        event_queue=queue.Queue(),
    )
    assert loop._role_configured("feature", "backend", "planner") is True
    assert loop._role_configured("feature", "backend", "qa_automation") is False


def test_role_configured_with_routing_rules(tmp_path):
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        routing_rules={"feature": {"backend": {"planner": "claude"}}},
    )
    sm = ConcreteStateMachine()
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=ArtifactStore(base=tmp_path / "art"),
        event_log=EventLog(path=tmp_path / "events.jsonl"),
        event_queue=queue.Queue(),
    )
    assert loop._role_configured("feature", "backend", "planner") is True


def test_run_role_calls_runner_and_returns_parsed_output(tmp_path):
    from system.orchestrator.schemas.artifacts import ParsedOutput
    from system.orchestrator.schemas.run_result import RunResult
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm, artifact_store=store,
        event_log=log, event_queue=queue.Queue(),
    )
    mock_runner = MagicMock()
    mock_runner.run.return_value = RunResult(
        status="completed", output='{"status":"pass","artifact_paths":[]}', exit_code=0
    )
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "do the work"
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[])
    env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    with patch.object(loop._router, "resolve", return_value=(mock_runner, mock_adapter)):
        result = loop._run_role(task, env, "doer")
    assert result.status == "pass"
    mock_runner.run.assert_called_once()


def test_persist_state_writes_yaml(tmp_path):
    import yaml
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        orchestrator=OrchestratorSettings(runtime_state=str(tmp_path / "state.yaml")),
    )
    sm = ConcreteStateMachine()
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=ArtifactStore(base=tmp_path / "art"),
        event_log=EventLog(path=tmp_path / "events.jsonl"),
        event_queue=queue.Queue(),
    )
    env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    loop._persist_state({"BRQ-1": (task, env)})
    data = yaml.safe_load((tmp_path / "state.yaml").read_text())
    assert "BRQ-1" in data["tasks"]
    assert data["tasks"]["BRQ-1"]["state"] == "READY_FOR_DOER"

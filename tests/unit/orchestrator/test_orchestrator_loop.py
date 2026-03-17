import queue
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import Task, TaskState, ConcreteStateMachine
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult


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

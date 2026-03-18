"""
Integration test: feed a local YAML task into the orchestrator loop.
Runners are mocked so no AI providers are needed.
Verifies: task loads → dep gate → NEW→SHAPING state transition → event emitted.
"""
import queue
import pytest
import yaml
from pathlib import Path
from system.orchestrator.config import OrchestratorConfig, GitHubConfig, OrchestratorSettings
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.event_log import EventLog
from system.orchestrator.local_task_loader import LocalYamlTaskLoader
from system.orchestrator.schemas.task_envelope import TaskEnvelope


TASK_YAML = {
    "task_id": "INT-1",
    "title": "Integration test task",
    "task_type": "feature",
    "component": "backend",
}


@pytest.fixture
def tmp_dirs(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "INT-1.yaml").write_text(yaml.dump(TASK_YAML))
    return tmp_path, tasks_dir


def test_new_task_transitions_to_shaping(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        orchestrator=OrchestratorSettings(poll_interval_seconds=0),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()

    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log, event_queue=eq,
    )

    # Load task
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    envelopes = loader.load_pending()
    assert len(envelopes) == 1
    tasks = [(Task(task_id=env.task_id, state=TaskState.NEW), env) for env in envelopes]

    # Run one tick
    task, env = tasks[0]
    updated_task = loop._tick(task, env, {task.task_id: (task, env)})

    # Task should have advanced to READY_FOR_SHAPING
    assert updated_task.state == TaskState.READY_FOR_SHAPING

    # Event should be in queue
    assert not eq.empty()
    event = eq.get_nowait()
    assert event.event_type == "state_transition"
    assert event.to_state == "READY_FOR_SHAPING"
    assert event.task_id == "INT-1"

    # Event should be in JSONL log
    events = log.tail(1)
    assert len(events) == 1
    assert events[0].to_state == "READY_FOR_SHAPING"


def _make_loop(tmp_path, tasks_dir):
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        orchestrator=OrchestratorSettings(poll_interval_seconds=0),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log, event_queue=eq,
        loader=loader,
    )
    return loop, eq


def test_hot_reload_picks_up_new_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, _ = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    assert "INT-1" in all_tasks
    assert all_tasks["INT-1"][0].state == TaskState.NEW


def test_hot_reload_cancels_deleted_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, eq = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    assert "INT-1" in all_tasks
    # Remove the task file
    (tasks_dir / "INT-1.yaml").unlink()
    loop._sync_tasks(all_tasks)
    assert "INT-1" not in all_tasks
    event = eq.get_nowait()
    assert event.event_type == "task_cancelled"
    assert event.task_id == "INT-1"
    assert event.from_state == "NEW"


def test_hot_reload_does_not_cancel_done_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, eq = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    # Advance task to DONE
    task, env = all_tasks["INT-1"]
    all_tasks["INT-1"] = (task.model_copy(update={"state": TaskState.DONE}), env)
    # Remove the file
    (tasks_dir / "INT-1.yaml").unlink()
    loop._sync_tasks(all_tasks)
    # DONE task stays in dict
    assert "INT-1" in all_tasks
    assert eq.empty()

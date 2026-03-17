import queue
import pytest
from system.orchestrator.tui.app import OrchestratorApp
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope


def test_app_instantiates():
    eq: queue.Queue = queue.Queue()
    env = TaskEnvelope(task_id="BRQ-1", title="Test", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    app = OrchestratorApp(event_queue=eq, tasks=[(task, env)])
    assert app is not None

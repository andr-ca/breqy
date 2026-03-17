import queue
from unittest.mock import MagicMock, patch
import pytest
from system.orchestrator.tui.app import OrchestratorApp
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.tui.panels.pipeline_panel import PipelinePanel
from system.orchestrator.tui.panels.task_panel import TaskPanel
from system.orchestrator.tui.panels.agent_panel import AgentPanel
from system.orchestrator.tui.panels.log_panel import LogPanel


def _make_task_and_env(task_id: str = "BRQ-1") -> tuple[Task, TaskEnvelope]:
    env = TaskEnvelope(task_id=task_id, title="Test", task_type="feature", component="backend")
    task = Task(task_id=task_id, state=TaskState.NEW)
    return task, env


def test_app_instantiates():
    eq: queue.Queue = queue.Queue()
    task, env = _make_task_and_env()
    app = OrchestratorApp(event_queue=eq, tasks=[(task, env)])
    assert app is not None


def test_app_instantiates_with_credential_store():
    eq: queue.Queue = queue.Queue()
    task, env = _make_task_and_env()
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        app = OrchestratorApp(event_queue=eq, tasks=[(task, env)], credential_store=store)
    assert app is not None
    assert app._providers is not None
    assert "claude" in app._providers


def test_app_providers_built_from_all_provider_classes():
    eq: queue.Queue = queue.Queue()
    task, env = _make_task_and_env()
    with patch("keyring.get_password", return_value=None):
        app = OrchestratorApp(event_queue=eq, tasks=[(task, env)])
    from system.orchestrator.auth import ALL_PROVIDER_CLASSES
    assert set(app._providers.keys()) == set(ALL_PROVIDER_CLASSES.keys())


# --- PipelinePanel unit tests ---

def test_pipeline_panel_instantiates():
    panel = PipelinePanel(id="pipeline")
    assert panel is not None


def test_pipeline_panel_handle_state_transition():
    panel = PipelinePanel(id="pipeline")
    # Before mounting the widget, query_one will raise; the panel catches it
    event = OrchestratorEvent(
        task_id="BRQ-1",
        event_type="state_transition",
        from_state="NEW",
        to_state="READY_FOR_SHAPING",
    )
    panel.handle_event(event)
    assert panel._current == "READY_FOR_SHAPING"


def test_pipeline_panel_handle_non_transition_event():
    panel = PipelinePanel(id="pipeline")
    event = OrchestratorEvent(
        task_id="BRQ-1",
        event_type="agent_spawn",
        notes="spawning",
    )
    panel.handle_event(event)
    assert panel._current is None


def test_pipeline_panel_completes_previous_state():
    panel = PipelinePanel(id="pipeline")
    event1 = OrchestratorEvent(
        task_id="BRQ-1", event_type="state_transition",
        from_state="NEW", to_state="READY_FOR_SHAPING",
    )
    event2 = OrchestratorEvent(
        task_id="BRQ-1", event_type="state_transition",
        from_state="READY_FOR_SHAPING", to_state="CODING",
    )
    panel.handle_event(event1)
    panel.handle_event(event2)
    assert "READY_FOR_SHAPING" in panel._completed
    assert panel._current == "CODING"


# --- TaskPanel unit tests ---

def test_task_panel_instantiates_with_tasks():
    task, env = _make_task_and_env()
    panel = TaskPanel(tasks=[(task, env)], id="task")
    assert panel._active_id == "BRQ-1"


def test_task_panel_instantiates_empty():
    panel = TaskPanel(tasks=[], id="task")
    assert panel._active_id is None


def test_task_panel_handle_event_unknown_task():
    task, env = _make_task_and_env()
    panel = TaskPanel(tasks=[(task, env)], id="task")
    event = OrchestratorEvent(task_id="UNKNOWN", event_type="state_transition", to_state="CODING")
    # Should not raise — task not found in dict, early return
    panel.handle_event(event)
    assert panel._active_id == "UNKNOWN"


def test_task_panel_handle_event_known_task():
    task, env = _make_task_and_env()
    panel = TaskPanel(tasks=[(task, env)], id="task")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition", to_state="CODING")
    # query_one raises (not mounted), caught internally
    panel.handle_event(event)
    assert panel._active_id == "BRQ-1"


# --- AgentPanel unit tests ---

def test_agent_panel_instantiates():
    panel = AgentPanel(id="agent")
    assert panel is not None


def test_agent_panel_handle_spawn_event():
    panel = AgentPanel(id="agent")
    event = OrchestratorEvent(
        task_id="BRQ-1", event_type="agent_spawn",
        role="dev", agent_type="claude", notes="spawning agent",
    )
    # query_one raises (not mounted), caught internally
    panel.handle_event(event)


def test_agent_panel_handle_irrelevant_event():
    panel = AgentPanel(id="agent")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition")
    panel.handle_event(event)


# --- LogPanel unit tests ---

def test_log_panel_instantiates():
    panel = LogPanel(id="log")
    assert panel is not None


def test_log_panel_handle_event():
    panel = LogPanel(id="log")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition", notes="moving state")
    # query_one raises (not mounted), caught internally
    panel.handle_event(event)


def test_log_panel_handle_unknown_event_type():
    panel = LogPanel(id="log")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="custom_event", notes="custom")
    panel.handle_event(event)

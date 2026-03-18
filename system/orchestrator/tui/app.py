# system/orchestrator/tui/app.py
from __future__ import annotations
import queue
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.containers import Horizontal, Vertical
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import Task
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.tui.panels.pipeline_panel import PipelinePanel
from system.orchestrator.tui.panels.task_panel import TaskPanel
from system.orchestrator.tui.panels.agent_panel import AgentPanel
from system.orchestrator.tui.panels.log_panel import LogPanel
from system.orchestrator.auth import ALL_PROVIDER_CLASSES
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.tui.panels.auth_panel import AuthPanel


class OrchestratorApp(App):
    CSS = """
    #top { height: 60%; }
    #pipeline { width: 35%; border: solid green; }
    #task { width: 65%; border: solid blue; }
    #agent { height: 25%; border: solid yellow; }
    #log { height: 15%; border: solid gray; }
    #auth-overlay {
        display: none;
        layer: overlay;
        height: 100%;
        width: 100%;
        border: double yellow;
        background: $surface;
    }
    """

    BINDINGS = [
        ("a", "toggle_auth", "Auth"),
        Binding("escape", "auth_back", "Back", priority=True),
    ]

    def __init__(self, event_queue: queue.Queue, tasks: list[tuple[Task, TaskEnvelope]], credential_store: CredentialStore | None = None) -> None:
        super().__init__()
        self._queue = event_queue
        self._tasks = tasks
        store = credential_store or CredentialStore()
        self._providers = {name: cls(credential_store=store) for name, cls in ALL_PROVIDER_CLASSES.items()}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="top"):
                yield PipelinePanel(id="pipeline")
                yield TaskPanel(tasks=self._tasks, id="task")
            yield AgentPanel(id="agent")
            yield LogPanel(id="log")
        yield Footer()
        yield AuthPanel(providers=self._providers, id="auth-overlay")

    def action_toggle_auth(self) -> None:
        panel = self.query_one("#auth-overlay", AuthPanel)
        panel.display = not panel.display

    def action_auth_back(self) -> None:
        """Escape: go back inside the auth panel, or close it if already on status."""
        panel = self.query_one("#auth-overlay", AuthPanel)
        if not panel.display:
            return
        if panel.current_view == "status":
            panel.display = False
        else:
            panel.action_cancel_auth()

    def on_mount(self) -> None:
        self.set_interval(0.5, self._poll_queue)

    def _poll_queue(self) -> None:
        while True:
            try:
                event: OrchestratorEvent = self._queue.get_nowait()
                self.query_one(PipelinePanel).handle_event(event)
                self.query_one(TaskPanel).handle_event(event)
                self.query_one(AgentPanel).handle_event(event)
                self.query_one(LogPanel).handle_event(event)
            except queue.Empty:
                break

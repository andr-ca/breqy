# system/orchestrator/tui/app.py
from __future__ import annotations
import queue
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Horizontal, Vertical
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.tui.panels.pipeline_panel import PipelinePanel
from system.orchestrator.tui.panels.task_panel import TaskPanel
from system.orchestrator.tui.panels.agent_panel import AgentPanel
from system.orchestrator.tui.panels.log_panel import LogPanel


class OrchestratorApp(App):
    CSS = """
    #top { height: 60%; }
    #pipeline { width: 35%; border: solid green; }
    #task { width: 65%; border: solid blue; }
    #agent { height: 25%; border: solid yellow; }
    #log { height: 15%; border: solid gray; }
    """

    def __init__(self, event_queue: queue.Queue, tasks: list[tuple[Task, TaskEnvelope]]) -> None:
        super().__init__()
        self._queue = event_queue
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="top"):
                yield PipelinePanel(id="pipeline")
                yield TaskPanel(tasks=self._tasks, id="task")
            yield AgentPanel(id="agent")
            yield LogPanel(id="log")
        yield Footer()

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

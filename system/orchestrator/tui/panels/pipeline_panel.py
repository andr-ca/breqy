# system/orchestrator/tui/panels/pipeline_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import Static
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import TaskState

_STATE_ORDER = list(TaskState)


class PipelinePanel(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._completed: set[str] = set()
        self._current: str | None = None
        self._current_task_id: str | None = None

    def compose(self):
        for state in _STATE_ORDER:
            yield Static(f"○ {state.value}", id=f"state-{state.value}")

    def handle_event(self, event: OrchestratorEvent) -> None:
        if event.event_type == "state_transition" and event.to_state:
            self._current_task_id = event.task_id
            if self._current is not None:
                self._completed.add(self._current)
            self._current = event.to_state
            for state in _STATE_ORDER:
                if state.value in self._completed:
                    label = "✓"
                elif state.value == self._current:
                    label = "●"
                else:
                    label = "○"
                try:
                    widget = self.query_one(f"#state-{state.value}", Static)
                    widget.update(f"{label} {state.value}")
                except Exception:
                    pass
        elif event.event_type == "task_cancelled":
            if event.task_id == self._current_task_id:
                self._current = None
                self._completed = set()
                self._current_task_id = None
                for state in _STATE_ORDER:
                    try:
                        widget = self.query_one(f"#state-{state.value}", Static)
                        widget.update(f"○ {state.value}")
                    except Exception:
                        pass

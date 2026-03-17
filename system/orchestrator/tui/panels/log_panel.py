# system/orchestrator/tui/panels/log_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import RichLog
from system.orchestrator.schemas.events import OrchestratorEvent

_COLOURS = {
    "state_transition": "green",
    "agent_spawn": "cyan",
    "agent_complete": "blue",
    "error": "red",
    "blocked": "red",
    "rate_limit": "yellow",
    "ci_result": "magenta",
}


class LogPanel(Widget):
    def compose(self):
        yield RichLog(id="event-log", markup=True)

    def handle_event(self, event: OrchestratorEvent) -> None:
        colour = _COLOURS.get(event.event_type, "white")
        ts = event.timestamp[11:19]   # HH:MM:SS
        msg = f"[{colour}]{ts}  {event.event_type:<22} {event.task_id}  {event.notes[:50]}[/{colour}]"
        try:
            self.query_one("#event-log", RichLog).write(msg)
        except Exception:
            pass

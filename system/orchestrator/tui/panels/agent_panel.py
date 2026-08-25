# system/orchestrator/tui/panels/agent_panel.py
from __future__ import annotations

from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import RichLog

from system.orchestrator.schemas.events import OrchestratorEvent


class AgentPanel(Widget):
    MAX_LINES = 50

    def compose(self):
        yield RichLog(id="agent-log", markup=True)

    def handle_event(self, event: OrchestratorEvent) -> None:
        if event.event_type in ("agent_spawn", "agent_complete"):
            try:
                log = self.query_one("#agent-log", RichLog)
                prefix = f"[{event.role}/{event.agent_type}]" if event.role else "[orchestrator]"
                log.write(f"{prefix} {event.notes}")
            except NoMatches:
                pass

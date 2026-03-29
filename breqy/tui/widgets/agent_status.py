"""AgentStatusBar widget — compact status line showing agent connection state.

Displays connected/disconnected agents with icons in a single-line ``Static``
widget.  Connected agents show a filled circle (``●``), disconnected agents
show a hollow circle (``○``).
"""
from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

from breqy.tui.constants import AGENT_CONNECTED_ICON, AGENT_DISCONNECTED_ICON


class AgentStatusBar(Widget):
    """Displays agent connection status as a compact status line."""

    DEFAULT_CSS = """
    AgentStatusBar {
        height: auto;
        max-height: 3;
    }
    """

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._agents: dict[str, bool] = {}
        self._model_info: tuple[str, str] | None = None

    def compose(self):  # noqa: ANN201
        yield Static("", id="agent-status")

    @property
    def status_widget(self) -> Static:
        """Return the inner Static widget."""
        return self.query_one("#agent-status", Static)

    def on_mount(self) -> None:
        """Render the empty state when the widget is first mounted."""
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def update_agent(self, agent_id: str, connected: bool) -> None:
        """Add or update an agent's connection status and re-render."""
        self._agents[agent_id] = connected
        self._refresh_display()

    def update_model_info(self, provider_id: str, model_id: str) -> None:
        """Store the active provider/model and re-render."""
        self._model_info = (provider_id, model_id)
        self._refresh_display()

    def clear_model_info(self) -> None:
        """Clear the model info and re-render."""
        self._model_info = None
        self._refresh_display()

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from tracking and re-render."""
        self._agents.pop(agent_id, None)
        self._refresh_display()

    def clear_agents(self) -> None:
        """Clear all tracked agents and re-render (shows empty state)."""
        self._agents.clear()
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Internal rendering
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_agent_name(agent_id: str) -> str:
        """Derive display name from agent_id, stripping ``agt_`` prefix."""
        if agent_id.startswith("agt_"):
            return agent_id[4:]
        return agent_id

    def _refresh_display(self) -> None:
        """Re-render the status line into the Static widget."""
        if not self._agents:
            self.status_widget.update("[dim]No agents[/dim]")
            return

        parts: list[str] = []
        for agent_id, connected in self._agents.items():
            name = self._format_agent_name(agent_id)
            if connected:
                icon = AGENT_CONNECTED_ICON
                parts.append(f"[green]{icon} {name}[/green]")
            else:
                icon = AGENT_DISCONNECTED_ICON
                parts.append(f"[dim]{icon} {name}[/dim]")

        line = " | ".join(parts)

        if self._model_info is not None:
            provider_id, model_id = self._model_info
            if provider_id == "null":
                line += f"  [dim]{provider_id} / {model_id}[/dim]"
            else:
                line += f"  [cyan]{provider_id} / {model_id}[/cyan]"

        self.status_widget.update(line)

# system/orchestrator/tui/auth_app.py
from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Footer, Header

from system.orchestrator.auth.base import AuthProvider
from system.orchestrator.tui.panels.auth_panel import AuthPanel


class AuthApp(App):
    """Standalone auth app — runs without the orchestrator loop."""

    CSS = """
    AuthPanel { height: 100%; border: solid green; }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "panel_back", "Back", priority=True),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, providers: dict[str, AuthProvider]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        yield Header()
        yield AuthPanel(providers=self._providers, id="auth-panel")
        yield Footer()

    def action_panel_back(self) -> None:
        """Escape — go back to status view inside the panel."""
        self.query_one("#auth-panel", AuthPanel).action_cancel_auth()

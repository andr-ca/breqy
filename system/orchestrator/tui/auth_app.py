# system/orchestrator/tui/auth_app.py
from __future__ import annotations
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from system.orchestrator.auth.base import AuthProvider
from system.orchestrator.tui.panels.auth_panel import AuthPanel


class AuthApp(App):
    """Standalone auth app — runs without the orchestrator loop."""

    CSS = """
    AuthPanel { height: 100%; border: solid green; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, providers: dict[str, AuthProvider]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        yield Header()
        yield AuthPanel(providers=self._providers, id="auth-panel")
        yield Footer()

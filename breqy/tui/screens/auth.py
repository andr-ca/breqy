"""AuthScreen — overlay screen for provider authentication management.

Displays a list of configured authentication providers with their current
status, and provides UI scaffolding for different auth flows (device code,
PKCE, and API key).

The screen does **not** perform actual authentication — it provides the UI
that the application (Task 15) drives by calling ``show_*`` methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static

from breqy.domain.enums import AuthFlowKind, AuthSessionStatus


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class ProviderInfo:
    """Describes a configured authentication provider."""

    name: str
    flow_kind: AuthFlowKind
    status: AuthSessionStatus = AuthSessionStatus.UNAUTHENTICATED


# --------------------------------------------------------------------------- #
# Status helpers
# --------------------------------------------------------------------------- #

_STATUS_ICONS: dict[AuthSessionStatus, str] = {
    AuthSessionStatus.UNAUTHENTICATED: "\u25cb",  # ○
    AuthSessionStatus.IN_PROGRESS: "\u25d4",       # ◔
    AuthSessionStatus.AUTHENTICATED: "\u25cf",     # ●
    AuthSessionStatus.FAILED: "\u2717",            # ✗
}

_FLOW_LABELS: dict[AuthFlowKind, str] = {
    AuthFlowKind.DEVICE: "Device Code",
    AuthFlowKind.PKCE_CODE: "PKCE",
    AuthFlowKind.API_KEY: "API Key",
}


# --------------------------------------------------------------------------- #
# AuthScreen
# --------------------------------------------------------------------------- #


class AuthScreen(Screen[None]):
    """Overlay screen for managing provider authentication.

    Layout::

        ┌─────────────────────────────────────────┐
        │  Authentication (header)                │
        ├─────────────────────────────────────────┤
        │  DataTable: providers list              │
        ├─────────────────────────────────────────┤
        │  Detail area (auth flow UI)             │
        ├─────────────────────────────────────────┤
        │  Footer: key hints                      │
        └─────────────────────────────────────────┘
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #

    class ProviderSelected(Message):
        """Posted when the user selects a provider row."""

        def __init__(self, provider: str) -> None:
            super().__init__()
            self.provider = provider

    class AuthFlowCompleted(Message):
        """Posted when an auth flow completes (success or failure)."""

        def __init__(self, provider: str, *, success: bool) -> None:
            super().__init__()
            self.provider = provider
            self.success = success

    # ------------------------------------------------------------------ #
    # Init
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        providers: list[ProviderInfo] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._providers: list[ProviderInfo] = (
            list(providers) if providers is not None else []
        )

    # ------------------------------------------------------------------ #
    # Compose
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Static("Authentication", id="auth-header")
        yield DataTable(id="auth-table")
        yield Vertical(id="auth-detail")
        yield Static(
            "[b]Escape[/b]=Back  [b]Enter[/b]=Select",
            id="auth-footer",
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        """Configure the DataTable columns and load initial data."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("", "Provider", "Flow Type", "Status")
        self.load_providers(self._providers)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def load_providers(self, providers: list[ProviderInfo]) -> None:
        """Clear and reload the DataTable with the given providers."""
        self._providers = list(providers)
        table = self.query_one(DataTable)
        table.clear()

        for provider in self._providers:
            icon = _STATUS_ICONS.get(provider.status, "?")
            flow_label = _FLOW_LABELS.get(provider.flow_kind, provider.flow_kind.value)
            table.add_row(
                icon,
                provider.name,
                flow_label,
                provider.status.value,
                key=provider.name,
            )

    def update_provider_status(
        self, name: str, status: AuthSessionStatus,
    ) -> None:
        """Update a provider's status in the internal list and DataTable."""
        for p in self._providers:
            if p.name == name:
                p.status = status
                break

        # Rebuild the table to reflect the change
        self.load_providers(self._providers)

    def show_device_flow(self, code: str, url: str) -> None:
        """Show device code flow UI in the detail area."""
        detail = self.query_one("#auth-detail", Vertical)
        detail.remove_children()
        detail.mount(Static(f"Code: {code}", id="device-code"))
        detail.mount(Static(f"URL: {url}", id="device-url"))

    def show_pkce_flow(self, url: str) -> None:
        """Show PKCE flow UI in the detail area."""
        detail = self.query_one("#auth-detail", Vertical)
        detail.remove_children()
        detail.mount(Static(f"URL: {url}", id="pkce-url"))
        detail.mount(Input(placeholder="Paste auth code...", id="pkce-input"))

    def show_api_key_flow(self) -> None:
        """Show API key input in the detail area."""
        detail = self.query_one("#auth-detail", Vertical)
        detail.remove_children()
        detail.mount(
            Input(placeholder="Enter API key...", password=True, id="api-key-input"),
        )

    def show_error(self, message: str) -> None:
        """Show an error message in the detail area."""
        detail = self.query_one("#auth-detail", Vertical)
        detail.remove_children()
        detail.mount(Static(message, id="auth-error"))

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_pop_screen(self) -> None:
        """Pop this screen (go back to previous)."""
        self.app.pop_screen()

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        """When a row is selected, post ProviderSelected with the provider name."""
        if event.row_key.value is not None:
            self.post_message(self.ProviderSelected(provider=str(event.row_key.value)))

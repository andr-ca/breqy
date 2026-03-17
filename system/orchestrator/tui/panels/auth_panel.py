# system/orchestrator/tui/panels/auth_panel.py
from __future__ import annotations
import threading
import time
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static, Input, Button, ContentSwitcher
from textual.containers import Vertical, Horizontal
from system.orchestrator.auth.base import AuthFlowType, AuthProvider, DeviceCodeResponse


class AuthPanel(Widget):
    """Interactive authentication panel for all runner providers."""

    def __init__(self, providers: dict[str, AuthProvider], **kwargs) -> None:
        super().__init__(**kwargs)
        self._providers = providers
        self._active_provider: str | None = None
        self._active_device_code: str | None = None
        self._poll_thread: threading.Thread | None = None

    def get_status_summary(self) -> dict[str, bool]:
        """Return {provider_name: is_authenticated} for all providers."""
        return {name: p.is_authenticated() for name, p in self._providers.items()}

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="status", id="auth-switcher"):
            with Vertical(id="status"):
                yield Static("[b]Runner Authentication[/b]", id="auth-title")
                table = DataTable(id="auth-table", cursor_type="row")
                yield table
                yield Static("↑↓ select runner · Enter to authenticate", id="auth-hint")

            with Vertical(id="device-flow"):
                yield Static("[b]Device Flow[/b]", id="df-title")
                yield Static("", id="df-url")
                yield Static("", id="df-code")
                yield Static("Waiting for authorization…", id="df-status")
                yield Button("Cancel", id="df-cancel", variant="error")

            with Vertical(id="pkce-flow"):
                yield Static("[b]PKCE Authorization[/b]", id="pkce-title")
                yield Static("", id="pkce-url")
                yield Static("Paste the authorization code:", id="pkce-hint")
                yield Input(placeholder="Paste code here", id="pkce-input")
                with Horizontal():
                    yield Button("Submit", id="pkce-submit", variant="primary")
                    yield Button("Cancel", id="pkce-cancel", variant="error")

            with Vertical(id="api-key-flow"):
                yield Static("[b]API Key[/b]", id="key-title")
                yield Input(placeholder="Paste API key", password=True, id="key-input")
                with Horizontal():
                    yield Button("Save", id="key-submit", variant="primary")
                    yield Button("Cancel", id="key-cancel", variant="error")

    def on_mount(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#auth-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Runner", "Flow", "Status")
        for name, provider in self._providers.items():
            status = "✓ authenticated" if provider.is_authenticated() else "✗ not authenticated"
            table.add_row(name, provider.flow_type.value, status, key=name)

    def _show_view(self, view_id: str) -> None:
        self.query_one("#auth-switcher", ContentSwitcher).current = view_id

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        provider_name = str(event.row_key.value)
        self._start_auth(provider_name)

    def _start_auth(self, provider_name: str) -> None:
        provider = self._providers.get(provider_name)
        if provider is None:
            return
        self._active_provider = provider_name

        if provider.flow_type == AuthFlowType.DEVICE_FLOW:
            device_resp = provider.request_device_code()
            self._active_device_code = device_resp.device_code
            url_markup = f"[link={device_resp.verification_uri}]{device_resp.verification_uri}[/link]"
            self.query_one("#df-url", Static).update(f"Open: {url_markup}")
            self.query_one("#df-code", Static).update(
                f"Enter code: [b]{device_resp.user_code}[/b]"
            )
            self.query_one("#df-status", Static).update("Waiting for authorization…")
            self._show_view("device-flow")
            self._start_device_poll(provider, device_resp)

        elif provider.flow_type == AuthFlowType.PKCE:
            url = provider.get_auth_url()
            url_markup = f"[link={url}]{url}[/link]"
            self.query_one("#pkce-url", Static).update(f"Open: {url_markup}")
            self.query_one("#pkce-input", Input).value = ""
            self._show_view("pkce-flow")

        elif provider.flow_type == AuthFlowType.API_KEY:
            self.query_one("#key-input", Input).value = ""
            self._show_view("api-key-flow")

    def _start_device_poll(self, provider: AuthProvider, device_resp: DeviceCodeResponse) -> None:
        def _poll() -> None:
            interval = max(device_resp.interval, 5)
            deadline = time.time() + device_resp.expires_in
            while time.time() < deadline:
                time.sleep(interval)
                token = provider.poll_for_token(device_resp.device_code)
                if token:
                    self.call_from_thread(self._on_auth_success)
                    return
            self.call_from_thread(self._on_device_expired)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

    def _on_auth_success(self) -> None:
        self._show_view("status")
        self._refresh_table()

    def _on_device_expired(self) -> None:
        self.query_one("#df-status", Static).update("[red]Expired — try again[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id in ("df-cancel", "pkce-cancel", "key-cancel"):
            self._show_view("status")

        elif btn_id == "pkce-submit":
            code = self.query_one("#pkce-input", Input).value.strip()
            if code and self._active_provider:
                provider = self._providers[self._active_provider]
                provider.exchange_code(code)
                self._on_auth_success()

        elif btn_id == "key-submit":
            key = self.query_one("#key-input", Input).value.strip()
            if key and self._active_provider:
                provider = self._providers[self._active_provider]
                provider.set_key(key)
                self._on_auth_success()

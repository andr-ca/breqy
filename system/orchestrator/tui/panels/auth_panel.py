# system/orchestrator/tui/panels/auth_panel.py
from __future__ import annotations
import threading
import time
from rich.markup import escape as markup_escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import DataTable, Static, Input, Button, ContentSwitcher
from textual.containers import Vertical, Horizontal
from system.orchestrator.auth.base import AuthFlowType, AuthProvider, DeviceCodeResponse


class AuthPanel(Widget):
    """Interactive authentication panel for all runner providers."""

    BINDINGS = [
        Binding("escape", "cancel_auth", "Back", priority=True),
        Binding("c", "copy_code", "Copy code"),
    ]

    def __init__(self, providers: dict[str, AuthProvider], **kwargs) -> None:
        super().__init__(**kwargs)
        self._providers = providers
        self._active_provider: str | None = None
        self._active_device_code: str | None = None
        self._active_user_code: str | None = None
        self._poll_thread: threading.Thread | None = None
        self._current_view: str = "status"

    @property
    def current_view(self) -> str:
        """Name of the currently visible sub-view."""
        return self._current_view

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
                yield Static("Press [b]c[/b] to copy code · [b]Esc[/b] to cancel", id="df-hint")
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

    def on_show(self) -> None:
        """Focus the table whenever the panel becomes visible."""
        self.query_one("#auth-table", DataTable).focus()

    def _refresh_table(self) -> None:
        table = self.query_one("#auth-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Runner", "Flow", "Status")
        for name, provider in self._providers.items():
            status = "✓ authenticated" if provider.is_authenticated() else "✗ not authenticated"
            table.add_row(name, provider.flow_type.value, status, key=name)

    def _show_view(self, view_id: str) -> None:
        self._current_view = view_id
        switcher = self.query_one("#auth-switcher", ContentSwitcher)
        switcher.current = view_id
        # Auto-focus first interactive element in the view
        if view_id == "status":
            table = self.query_one("#auth-table", DataTable)
            table.focus()
        elif view_id == "device-flow":
            btn = self.query_one("#df-cancel", Button)
            btn.focus()
        elif view_id == "pkce-flow":
            input_widget = self.query_one("#pkce-input", Input)
            input_widget.focus()
        elif view_id == "api-key-flow":
            input_widget = self.query_one("#key-input", Input)
            input_widget.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        provider_name = str(event.row_key.value)
        self._start_auth(provider_name)

    def _start_auth(self, provider_name: str) -> None:
        provider = self._providers.get(provider_name)
        if provider is None:
            return
        self._active_provider = provider_name

        if provider.flow_type == AuthFlowType.DEVICE_FLOW:
            try:
                device_resp = provider.request_device_code()
                self._active_device_code = device_resp.device_code
                self._active_user_code = device_resp.user_code
                self._show_view("device-flow")
                url = device_resp.verification_uri
                url_text = Text("Open: ")
                url_text.append(url, style=f"link {url}")
                self.query_one("#df-url", Static).update(url_text)
                self.query_one("#df-code", Static).update(
                    f"Enter code: [b]{markup_escape(device_resp.user_code)}[/b]"
                )
                copied = self._copy_to_clipboard(device_resp.user_code)
                status = "Waiting… (code copied to clipboard)" if copied else "Waiting… (press c to copy code)"
                self.query_one("#df-status", Static).update(status)
                self._start_device_poll(provider, device_resp)
            except Exception as e:
                self._show_view("device-flow")
                self.query_one("#df-url", Static).update("")
                self.query_one("#df-code", Static).update("")
                self.query_one("#df-status", Static).update(
                    f"[red]Error: {markup_escape(str(e))}[/red]"
                )

        elif provider.flow_type == AuthFlowType.PKCE:
            try:
                url = provider.get_auth_url()
                self._show_view("pkce-flow")
                url_text = Text("Open: ")
                url_text.append(url, style=f"link {url}")
                self.query_one("#pkce-url", Static).update(url_text)
                self.query_one("#pkce-input", Input).value = ""
            except Exception as e:
                self._show_view("pkce-flow")
                self.query_one("#pkce-url", Static).update(
                    f"[red]Error: {markup_escape(str(e))}[/red]"
                )

        elif provider.flow_type == AuthFlowType.API_KEY:
            try:
                self._show_view("api-key-flow")
                self.query_one("#key-input", Input).value = ""
            except Exception as e:
                self.query_one("#key-title", Static).update(f"[red]Error: {e}[/red]")

    def _start_device_poll(self, provider: AuthProvider, device_resp: DeviceCodeResponse) -> None:
        # Capture app reference in main thread — ContextVar not available in background threads
        app = self.app

        def _update_status(msg: str) -> None:
            try:
                self.query_one("#df-status", Static).update(msg)
            except Exception:
                pass

        def _poll() -> None:
            interval = max(device_resp.interval, 5)
            deadline = time.time() + device_resp.expires_in
            attempt = 0
            # Check first, sleep after — avoids a full interval delay before the first poll
            while time.time() < deadline:
                attempt += 1
                app.call_from_thread(_update_status, f"Checking… (attempt {attempt})")
                try:
                    token = provider.poll_for_token(device_resp.device_code)
                except RuntimeError as e:
                    # Fatal: unexpected response format or exchange failure — stop polling
                    app.call_from_thread(
                        _update_status,
                        f"[red]Auth failed: {markup_escape(str(e))}[/red]",
                    )
                    return
                except Exception as e:
                    # Transient: network error etc — keep retrying
                    app.call_from_thread(
                        _update_status,
                        f"[yellow]Poll error, retrying: {markup_escape(str(e))}[/yellow]",
                    )
                else:
                    if token:
                        app.call_from_thread(self._on_auth_success)
                        return
                    app.call_from_thread(
                        _update_status, f"Waiting for authorization… (attempt {attempt})"
                    )
                time.sleep(interval)
            app.call_from_thread(self._on_device_expired)

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
            self._submit_pkce()
        elif btn_id == "key-submit":
            self._submit_api_key()

    def action_cancel_auth(self) -> None:
        """Handle Escape key — go back to status view."""
        if self._current_view != "status":
            self._show_view("status")

    def action_copy_code(self) -> None:
        """Copy device user_code to clipboard when in device-flow view."""
        if self._current_view != "device-flow" or not self._active_user_code:
            return
        copied = self._copy_to_clipboard(self._active_user_code)
        try:
            msg = "[green]Copied![/green]" if copied else "[red]Clipboard unavailable[/red]"
            self.query_one("#df-status", Static).update(msg)
        except Exception:
            pass

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to system clipboard. Returns True on success."""
        import subprocess
        # Try X11 and Wayland clipboard tools directly
        for cmd in (
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["wl-copy"],
        ):
            try:
                result = subprocess.run(
                    cmd, input=text.encode(), timeout=2, capture_output=True
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        # Fallback: pyperclip handles additional platforms
        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input fields — submit the form."""
        input_id = event.input.id
        if input_id == "pkce-input":
            self._submit_pkce()
        elif input_id == "key-input":
            self._submit_api_key()

    def _submit_pkce(self) -> None:
        """Submit PKCE authorization code."""
        code = self.query_one("#pkce-input", Input).value.strip()
        if code and self._active_provider:
            provider = self._providers[self._active_provider]
            try:
                provider.exchange_code(code)
                self._on_auth_success()
            except Exception as e:
                self.query_one("#pkce-url", Static).update(
                    f"[red]Error: {markup_escape(str(e))}[/red]"
                )

    def _submit_api_key(self) -> None:
        """Submit API key."""
        key = self.query_one("#key-input", Input).value.strip()
        if key and self._active_provider:
            provider = self._providers[self._active_provider]
            try:
                provider.set_key(key)
                self._on_auth_success()
            except Exception as e:
                self.query_one("#key-title", Static).update(
                    f"[red]Error: {markup_escape(str(e))}[/red]"
                )

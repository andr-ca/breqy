"""SessionListScreen — displays all sessions in a DataTable.

The screen is the main entry point of the Breqy TUI.  Users can select a
session to open, create a new session, refresh the list, or quit.
"""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Static

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session

# --------------------------------------------------------------------------- #
# Status helpers
# --------------------------------------------------------------------------- #

_STATUS_ICONS: dict[SessionStatus, str] = {
    SessionStatus.ACTIVE: "\u25cf",         # ●
    SessionStatus.CLOSED: "\u25cb",         # ○
    SessionStatus.SUSPENDED: "\u25d4",      # ◔
    SessionStatus.CIRCUIT_BROKEN: "\u2717", # ✗
}


def _format_timestamp(dt: datetime) -> str:
    """Return a human-friendly timestamp string."""
    return dt.strftime("%Y-%m-%d %H:%M")


def _truncate_id(session_id: str, max_len: int = 20) -> str:
    """Truncate a session id for display."""
    if len(session_id) <= max_len:
        return session_id
    return session_id[: max_len - 1] + "\u2026"


# --------------------------------------------------------------------------- #
# SessionListScreen
# --------------------------------------------------------------------------- #


class SessionListScreen(Screen):
    """Screen that lists all Breqy sessions in a DataTable."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("n", "new_session", "New Session", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #

    class SessionSelected(Message):
        """Posted when the user selects a session row."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class NewSessionRequested(Message):
        """Posted when the user presses N to create a new session."""

    class RefreshRequested(Message):
        """Posted when the user presses R to refresh the list."""

    # ------------------------------------------------------------------ #
    # Init
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        sessions: list[Session] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._sessions: list[Session] = sessions if sessions is not None else []

    # ------------------------------------------------------------------ #
    # Compose
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Static("Breqy \u2014 Sessions", id="session-list-header")
        yield DataTable(id="session-table")
        yield Static(
            "[dim]No sessions yet. Press N to create one.[/dim]",
            id="empty-sessions",
        )
        yield Static(
            "[b]N[/b] New  [b]R[/b] Refresh  [b]Q[/b] Quit  [b]Enter[/b] Open",
            id="session-list-footer",
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        """Configure the DataTable columns and load initial data."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("", "Session ID", "Agent", "Created", "Status")
        self.load_sessions(self._sessions)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def load_sessions(self, sessions: list[Session]) -> None:
        """Clear and reload the DataTable with the given sessions."""
        self._sessions = list(sessions)
        table = self.query_one(DataTable)
        table.clear()

        empty_label = self.query_one("#empty-sessions", Static)

        if not sessions:
            empty_label.display = True
            return

        empty_label.display = False
        for session in sessions:
            icon = _STATUS_ICONS.get(session.status, "?")
            css_class = self._status_class(session.status)
            status_text = f"[{css_class}]{session.status.value}[/{css_class}]"
            icon_text = f"[{css_class}]{icon}[/{css_class}]"
            table.add_row(
                icon_text,
                _truncate_id(session.id),
                session.primary_agent_id,
                _format_timestamp(session.created_at),
                status_text,
                key=session.id,
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _status_class(status: SessionStatus) -> str:
        """Map a session status to its CSS class name."""
        return f"session-{status.value.replace('_', '-')}"

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_new_session(self) -> None:
        """Post a NewSessionRequested message."""
        self.post_message(self.NewSessionRequested())

    def action_refresh(self) -> None:
        """Post a RefreshRequested message."""
        self.post_message(self.RefreshRequested())

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        """When a row is selected, post SessionSelected with the session id."""
        if event.row_key.value is not None:
            self.post_message(self.SessionSelected(session_id=str(event.row_key.value)))

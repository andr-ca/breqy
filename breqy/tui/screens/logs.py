"""LogsScreen — overlay screen for viewing event logs and Python log entries.

Displays a live stream of domain events (Events view) or Python structlog
entries (Logs view) with timestamp, source/level, event type/logger, and
summary/message.  Supports filtering and uses ring buffers to limit memory.

Toggle between views with the ``Tab`` key.
Push as an overlay from the app's ``ctrl+l`` binding.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from datetime import datetime

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from breqy.tui.widgets.selectable_rich_log import SelectableRichLog


@dataclass
class LogEntry:
    """A single domain-event log entry."""

    timestamp: datetime
    source: str
    event_type: str
    summary: str


@dataclass
class PythonLogEntry:
    """A Python log entry from structlog."""

    timestamp: datetime
    level: str
    logger_name: str
    message: str
    extra: dict[str, str] = field(default_factory=dict)


class LogsScreen(Screen[None]):
    """Overlay screen for viewing event logs with filtering and dual view.

    Layout::

        ┌─────────────────────────────────────────────┐
        │  Static("Event Logs" / "Python Logs")       │
        ├─────────────────────────────────────────────┤
        │  Input(placeholder="Filter…")               │
        ├─────────────────────────────────────────────┤
        │  RichLog (scrollable log display)           │
        ├─────────────────────────────────────────────┤
        │  Static (key hints)                         │
        └─────────────────────────────────────────────┘
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("c", "clear_filter", "Clear filter", show=True),
        Binding("tab", "toggle_view", "Toggle Events/Logs", show=True),
    ]

    def __init__(self, max_entries: int = 500, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._entries: collections.deque[LogEntry] = collections.deque(maxlen=max_entries)
        self._log_entries: collections.deque[PythonLogEntry] = collections.deque(maxlen=max_entries)
        self._filter_prefix: str = ""
        self._view_mode: str = "events"

    # ------------------------------------------------------------------ #
    # Compose
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        """Yield the logs screen layout."""
        yield Static("Event Logs", id="logs-header")
        yield Input(placeholder="Filter by event type...", id="filter-input")
        yield SelectableRichLog(id="logs-display", wrap=True, markup=True)
        yield Static(
            "[b]Escape[/b] Back  [b]Tab[/b] Events/Logs  [b]C[/b] Clear filter",
            id="logs-footer",
        )

    def on_mount(self) -> None:
        """Pre-populate from app's log buffer (if available), then render."""
        buffer = getattr(self.app, "_log_buffer", None)
        if buffer:
            for entry in buffer:
                if entry not in self._entries:
                    self._entries.append(entry)
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Input change handler
    # ------------------------------------------------------------------ #

    @on(Input.Changed, "#filter-input")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        """Update the filter when the input value changes."""
        self.set_filter(event.value)

    # ------------------------------------------------------------------ #
    # Public API — domain events
    # ------------------------------------------------------------------ #

    def add_event(
        self,
        timestamp: datetime,
        source: str,
        event_type: str,
        summary: str,
    ) -> None:
        """Add a domain-event entry to the ring buffer and refresh display."""
        entry = LogEntry(
            timestamp=timestamp,
            source=source,
            event_type=event_type,
            summary=summary,
        )
        self._entries.append(entry)
        if self._view_mode == "events":
            self._refresh_display()

    # ------------------------------------------------------------------ #
    # Public API — Python log entries
    # ------------------------------------------------------------------ #

    def add_log_entry(
        self,
        timestamp: datetime,
        level: str,
        logger_name: str,
        message: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        """Add a Python log entry to the ring buffer and refresh display."""
        entry = PythonLogEntry(
            timestamp=timestamp,
            level=level,
            logger_name=logger_name,
            message=message,
            extra=extra or {},
        )
        self._log_entries.append(entry)
        if self._view_mode == "logs":
            self._refresh_display()

    # ------------------------------------------------------------------ #
    # View mode toggle
    # ------------------------------------------------------------------ #

    def toggle_view(self) -> None:
        """Switch between events and logs view."""
        self._view_mode = "logs" if self._view_mode == "events" else "events"
        self._update_header()
        self._refresh_display()

    def _update_header(self) -> None:
        """Update the header text to reflect the current view mode."""
        try:
            header = self.query_one("#logs-header", Static)
            header.update("Python Logs" if self._view_mode == "logs" else "Event Logs")
        except Exception:
            pass  # Header may not be mounted yet

    # ------------------------------------------------------------------ #
    # Filter
    # ------------------------------------------------------------------ #

    def set_filter(self, prefix: str) -> None:
        """Filter displayed entries by prefix."""
        self._filter_prefix = prefix
        self._refresh_display()

    def clear_filter(self) -> None:
        """Remove filter, show all entries."""
        self._filter_prefix = ""
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = ""
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_pop_screen(self) -> None:
        """Pop this screen (go back to previous screen)."""
        self.app.pop_screen()

    def action_clear_filter(self) -> None:
        """Clear the active filter via key binding."""
        self.clear_filter()

    def action_toggle_view(self) -> None:
        """Toggle view mode via key binding."""
        self.toggle_view()

    # ------------------------------------------------------------------ #
    # Internal rendering
    # ------------------------------------------------------------------ #

    def _get_visible_entries(self) -> list[LogEntry]:
        """Return domain-event entries matching the current filter."""
        if not self._filter_prefix:
            return list(self._entries)
        prefix = self._filter_prefix.lower()
        return [
            entry
            for entry in self._entries
            if entry.event_type.lower().startswith(prefix)
            or entry.source.lower().startswith(prefix)
        ]

    def _get_visible_log_entries(self) -> list[PythonLogEntry]:
        """Return Python log entries matching the current filter."""
        if not self._filter_prefix:
            return list(self._log_entries)
        return [
            e
            for e in self._log_entries
            if e.level.startswith(self._filter_prefix.upper())
            or e.logger_name.startswith(self._filter_prefix)
        ]

    def _refresh_display(self) -> None:
        """Clear and re-render visible entries based on current view mode."""
        try:
            log = self.query_one("#logs-display", RichLog)
        except Exception:
            return  # Not mounted yet

        log.clear()

        if self._view_mode == "events":
            visible = self._get_visible_entries()
            if not visible:
                log.write("[dim]No events[/dim]")
                return
            for entry in visible:
                ts_str = entry.timestamp.strftime("%H:%M:%S")
                log.write(
                    f"[dim]{ts_str}[/dim] [{entry.source}] "
                    f"[bold]{entry.event_type}[/bold] {entry.summary}"
                )
        else:
            visible_logs = self._get_visible_log_entries()
            if not visible_logs:
                log.write("[dim]No log entries[/dim]")
                return
            _level_colors = {
                "DEBUG": "dim",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
            }
            for log_entry in visible_logs:
                ts_str = log_entry.timestamp.strftime("%H:%M:%S")
                color = _level_colors.get(log_entry.level, "")
                level_fmt = f"[{color}]{log_entry.level}[/{color}]" if color else log_entry.level
                log.write(
                    f"[dim]{ts_str}[/dim] {level_fmt} "
                    f"[bold]{log_entry.logger_name}[/bold] {log_entry.message}"
                )

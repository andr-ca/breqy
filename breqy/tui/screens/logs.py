"""LogsScreen — overlay screen for viewing event logs.

Displays a live stream of domain events with timestamp, source, event type,
and summary.  Supports filtering by event type prefix and uses a ring buffer
(``collections.deque``) to limit memory usage.

Push as an overlay from the app's ``ctrl+l`` binding.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import datetime

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static


@dataclass
class LogEntry:
    """A single event log entry."""

    timestamp: datetime
    source: str
    event_type: str
    summary: str


class LogsScreen(Screen[None]):
    """Overlay screen for viewing event logs with filtering.

    Layout::

        ┌─────────────────────────────────────────────┐
        │  Static("Event Logs")                       │
        ├─────────────────────────────────────────────┤
        │  Input(placeholder="Filter by event type…") │
        ├─────────────────────────────────────────────┤
        │  RichLog (scrollable log display)           │
        ├─────────────────────────────────────────────┤
        │  Static (key hints: Escape=Back, C=Clear)   │
        └─────────────────────────────────────────────┘
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("c", "clear_filter", "Clear filter", show=True),
    ]

    def __init__(self, max_entries: int = 500, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._entries: collections.deque[LogEntry] = collections.deque(maxlen=max_entries)
        self._filter_prefix: str = ""

    # ------------------------------------------------------------------ #
    # Compose
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        """Yield the logs screen layout."""
        yield Static("Event Logs", id="logs-header")
        yield Input(placeholder="Filter by event type...", id="filter-input")
        yield RichLog(id="logs-display", wrap=True, markup=True)
        yield Static(
            "[b]Escape[/b] Back  [b]C[/b] Clear filter",
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
    # Public API
    # ------------------------------------------------------------------ #

    def add_event(
        self,
        timestamp: datetime,
        source: str,
        event_type: str,
        summary: str,
    ) -> None:
        """Add a log entry to the ring buffer and refresh display."""
        entry = LogEntry(
            timestamp=timestamp,
            source=source,
            event_type=event_type,
            summary=summary,
        )
        self._entries.append(entry)
        self._refresh_display()

    def set_filter(self, prefix: str) -> None:
        """Filter displayed events to those whose event_type starts with prefix."""
        self._filter_prefix = prefix
        self._refresh_display()

    def clear_filter(self) -> None:
        """Remove filter, show all events."""
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

    # ------------------------------------------------------------------ #
    # Internal rendering
    # ------------------------------------------------------------------ #

    def _get_visible_entries(self) -> list[LogEntry]:
        """Return entries matching the current filter."""
        if not self._filter_prefix:
            return list(self._entries)
        return [
            entry
            for entry in self._entries
            if entry.event_type.startswith(self._filter_prefix)
        ]

    def _refresh_display(self) -> None:
        """Clear and re-render all visible log entries."""
        log = self.query_one("#logs-display", RichLog)
        log.clear()

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

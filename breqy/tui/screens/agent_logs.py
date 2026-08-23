"""AgentLogsScreen — overlay screen for live-tailing the agent log file.

Opens as a Textual overlay pushed by ``BreqyApp.on_command_executed`` when
the user types ``/logs``.  Reads the agent subprocess log file (written by
the agent process with ``console=False``) and tails it every 0.5 s.

Pure helpers (importable without a running Textual app):
  - ``resolve_agent_log_path(agent_id)`` — resolves the log file path
  - ``read_tail(path, n)`` — reads the last *n* lines from a file
  - ``read_new_lines(path, offset)`` — returns bytes written after *offset*
  - ``filter_lines(lines, filter_str)`` — case-insensitive substring filter
"""

from __future__ import annotations

import collections
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from breqy.tui.widgets.selectable_rich_log import SelectableRichLog

# ---------------------------------------------------------------------------
# Pure helper utilities (testable without Textual)
# ---------------------------------------------------------------------------

_WAITING_PLACEHOLDER = "Waiting for log file…"
_TAIL_LINES = 200
_MAX_BUFFER_LINES = 1000


def resolve_agent_log_path(agent_id: str) -> Path:
    """Return the agent log file path for *agent_id*.

    Uses ``BREQY_DATA_DIR`` env var when set, otherwise defaults to
    ``~/.breqy/data``.  If *agent_id* is empty the file is named
    ``agent.log`` (no-ID convention from :func:`breqy.utils.logging.default_log_file`).
    """
    data_dir = Path(os.environ.get("BREQY_DATA_DIR", "~/.breqy/data")).expanduser()
    log_dir = data_dir / "logs"
    if agent_id:
        return log_dir / f"agent-{agent_id}.log"
    return log_dir / "agent.log"


def read_tail(path: Path, n: int = _TAIL_LINES) -> str:
    """Return the last *n* lines of *path* as a single string.

    Returns:
        The last *n* lines joined by newlines.  An empty string if the file
        is empty.  The ``_WAITING_PLACEHOLDER`` message if the file does not
        exist.  Silently returns an empty string on other ``OSError``.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return _WAITING_PLACEHOLDER
    except OSError:
        return ""

    if not text:
        return ""

    lines = text.splitlines()
    return "\n".join(lines[-n:])


def read_new_lines(path: Path, offset: int) -> tuple[str, int]:
    """Return any bytes written to *path* after byte *offset*.

    Returns:
        A ``(new_text, new_offset)`` tuple.  *new_text* is the text added
        since *offset*; *new_offset* is the new file position.  On any
        ``OSError`` returns ``("", offset)`` — the offset is unchanged so
        the next poll retries from the same position.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_text = f.read()
            new_offset = f.tell()
        return new_text, new_offset
    except OSError:
        return "", offset


def filter_lines(lines: Iterable[str], filter_str: str) -> list[str]:
    """Return lines containing *filter_str* (case-insensitive).

    If *filter_str* is empty, all lines are returned.
    """
    if not filter_str:
        return list(lines)
    needle = filter_str.lower()
    return [line for line in lines if needle in line.lower()]


# ---------------------------------------------------------------------------
# AgentLogsScreen
# ---------------------------------------------------------------------------


class AgentLogsScreen(Screen[None]):
    """Overlay screen that live-tails the agent subprocess log file.

    Layout::

        ┌─────────────────────────────────────────────────────┐
        │  Agent Logs  ~/.breqy/data/logs/agent-breqy.log     │
        ├─────────────────────────────────────────────────────┤
        │  Filter: [____________]                             │
        ├─────────────────────────────────────────────────────┤
        │                                                     │
        │  SelectableRichLog (scrollable, text-selectable)    │
        │  — last 200 lines pre-loaded on open               │
        │  — new lines appended every 0.5 s via set_interval │
        │                                                     │
        └─── q/Esc close  F filter  C clear ────────────────┘
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "pop_screen", "Close", show=True),
        Binding("q", "pop_screen", "Close", show=True),
        Binding("f", "focus_filter", "Filter", show=True),
        Binding("c", "clear_filter", "Clear filter", show=True),
    ]

    def __init__(
        self,
        log_file: Path | None = None,
        agent_id: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._log_file: Path = (
            log_file if log_file is not None else resolve_agent_log_path(agent_id)
        )
        self._offset: int = 0
        self._lines: collections.deque[str] = collections.deque(maxlen=_MAX_BUFFER_LINES)
        self._filter: str = ""

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Yield the agent logs screen layout."""
        yield Static(f"Agent Logs  {self._log_file}", id="agent-logs-header")
        yield Input(placeholder="Filter…", id="agent-logs-filter")
        yield SelectableRichLog(id="agent-logs-display", wrap=True, markup=False)
        yield Static(
            "[b]Escape[/b]/[b]q[/b] Close  [b]f[/b] Filter  [b]c[/b] Clear filter",
            id="agent-logs-footer",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Pre-load the last 200 lines and start the polling interval."""
        self._load_initial_lines()
        self.set_interval(0.5, self._poll_log)

    # ------------------------------------------------------------------
    # Input handler
    # ------------------------------------------------------------------

    @on(Input.Changed, "#agent-logs-filter")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        """Update filter and re-render when the user types in the filter box."""
        self._filter = event.value.strip().lower()
        self._refresh_display()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_initial_lines(self) -> None:
        """Read last _TAIL_LINES lines into the buffer, then render."""
        initial_text = read_tail(self._log_file, n=_TAIL_LINES)
        if initial_text:
            self._lines.extend(initial_text.splitlines())
        self._refresh_display()
        # Seek to end so subsequent polls only return new content
        try:
            self._offset = self._log_file.stat().st_size
        except OSError:
            self._offset = 0

    def _poll_log(self) -> None:
        """Append any new log lines written since the last poll."""
        new_text, new_offset = read_new_lines(self._log_file, self._offset)
        self._offset = new_offset
        if not new_text:
            return

        new_lines = new_text.splitlines()
        self._lines.extend(new_lines)  # always update buffer first

        if self._filter:
            # Filter active: full re-render to include any new matches
            self._refresh_display()
        else:
            # Fast path: append directly without clearing the display
            display = self.query_one("#agent-logs-display", RichLog)
            display.write(new_text)

    def _refresh_display(self) -> None:
        """Clear the log display and re-render from the buffer."""
        try:
            display = self.query_one("#agent-logs-display", RichLog)
        except NoMatches:
            return  # not mounted yet

        display.clear()
        for line in filter_lines(self._lines, self._filter):
            display.write(line)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_pop_screen(self) -> None:
        """Pop this screen (close the overlay)."""
        self.app.pop_screen()

    def action_focus_filter(self) -> None:
        """Move keyboard focus to the filter Input."""
        self.query_one("#agent-logs-filter", Input).focus()

    def action_clear_filter(self) -> None:
        """Clear the active filter and reset the Input widget."""
        self._filter = ""
        filter_input = self.query_one("#agent-logs-filter", Input)
        filter_input.value = ""
        filter_input.focus()
        self._refresh_display()

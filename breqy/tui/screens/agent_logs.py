"""AgentLogsScreen — overlay screen for live-tailing the agent log file.

Opens as a Textual overlay pushed by ``BreqyApp.on_command_executed`` when
the user types ``/logs``.  Reads the agent subprocess log file (written by
the agent process with ``console=False``) and tails it every 0.5 s.

Pure helpers (importable without a running Textual app):
  - ``resolve_agent_log_path(agent_id)`` — resolves the log file path
  - ``read_tail(path, n)`` — reads the last *n* lines from a file
  - ``read_new_lines(path, offset)`` — returns bytes written after *offset*
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import RichLog, Static

from breqy.tui.widgets.selectable_rich_log import SelectableRichLog

# ---------------------------------------------------------------------------
# Pure helper utilities (testable without Textual)
# ---------------------------------------------------------------------------

_WAITING_PLACEHOLDER = "Waiting for log file…"
_TAIL_LINES = 200


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
        │                                                     │
        │  SelectableRichLog (scrollable, text-selectable)    │
        │  — last 200 lines pre-loaded on open               │
        │  — new lines appended every 0.5 s via set_interval │
        │                                                     │
        └─── q / Escape to close ────────────────────────────┘
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Close", show=True),
        Binding("q", "pop_screen", "Close", show=True),
    ]

    def __init__(
        self,
        log_file: Path | None = None,
        agent_id: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._log_file: Path = (
            log_file if log_file is not None else resolve_agent_log_path(agent_id)
        )
        self._offset: int = 0

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Yield the agent logs screen layout."""
        yield Static(f"Agent Logs  {self._log_file}", id="agent-logs-header")
        yield SelectableRichLog(id="agent-logs-display", wrap=True, markup=False)
        yield Static(
            "[b]Escape[/b] / [b]q[/b]  Close",
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
    # Internal
    # ------------------------------------------------------------------

    def _load_initial_lines(self) -> None:
        """Read and display the last _TAIL_LINES lines from the log file."""
        display = self.query_one("#agent-logs-display", RichLog)
        initial_text = read_tail(self._log_file, n=_TAIL_LINES)
        if initial_text:
            display.write(initial_text)
        # Seek to end so subsequent polls only return new content
        try:
            self._offset = self._log_file.stat().st_size
        except OSError:
            self._offset = 0

    def _poll_log(self) -> None:
        """Append any new log lines written since the last poll."""
        new_text, new_offset = read_new_lines(self._log_file, self._offset)
        self._offset = new_offset
        if new_text:
            display = self.query_one("#agent-logs-display", RichLog)
            display.write(new_text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_pop_screen(self) -> None:
        """Pop this screen (close the overlay)."""
        self.app.pop_screen()

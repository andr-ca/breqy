# AgentLogsScreen Search/Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live-filtering search bar to `AgentLogsScreen` that instantly shows only lines matching a case-insensitive substring, while continuing to live-tail the log file.

**Architecture:** A `filter_lines()` pure helper performs case-insensitive substring filtering. `AgentLogsScreen` gains a `_lines: deque[str]` ring buffer (maxlen=1000) and a `_filter: str`. On filter change the display is cleared and re-rendered from the buffer. On poll, new lines extend the buffer first; the fast path (no filter) writes directly to `RichLog`, the slow path (filter active) calls full `_refresh_display()`.

**Tech Stack:** Python 3.12, Textual, `collections.deque`, pytest

**Spec:** `docs/superpowers/specs/2026-04-04-agent-logs-search-design.md`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `breqy/tui/screens/agent_logs.py` | Modify | Add `filter_lines()` helper; add `_lines`/`_filter` state; add `Input` widget; update `compose`, `__init__`, `_load_initial_lines`, `_poll_log`; add `_refresh_display`, `_on_filter_changed`, `action_clear_filter`, `action_focus_filter`; add `f`/`c` bindings |
| `tests/unit/tui/test_agent_logs_screen.py` | Modify | Add `TestFilterLines` class with 5 new tests for the `filter_lines` pure helper |

No other files change.

---

## Task 1: `filter_lines()` pure helper — RED → GREEN

**Files:**
- Modify: `tests/unit/tui/test_agent_logs_screen.py`
- Modify: `breqy/tui/screens/agent_logs.py`

### Step 1: Write failing tests for `filter_lines`

Add the following class to the **bottom** of `tests/unit/tui/test_agent_logs_screen.py`:

```python
# ---------------------------------------------------------------------------
# Pure helper: filter_lines
# ---------------------------------------------------------------------------


class TestFilterLines:
    """filter_lines returns only lines containing the filter substring."""

    def test_filter_lines_hides_non_matching(self) -> None:
        """Lines not containing the filter string are excluded."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["info: provider started", "debug: tool called", "info: stream ended"]
        result = filter_lines(lines, "info")
        assert result == ["info: provider started", "info: stream ended"]

    def test_filter_lines_empty_returns_all(self) -> None:
        """Empty filter string returns all lines unchanged."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["line a", "line b", "line c"]
        result = filter_lines(lines, "")
        assert result == ["line a", "line b", "line c"]

    def test_filter_lines_is_case_insensitive(self) -> None:
        """Lowercase filter matches uppercase content and vice versa."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["INFO: started", "DEBUG: called", "WARNING: slow"]
        result = filter_lines(lines, "info")
        assert result == ["INFO: started"]

    def test_filter_lines_partial_match(self) -> None:
        """Substring match — does not require full-line equality."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ['{"event": "llm_call", "initiator": "user"}',
                 '{"event": "tool_result", "initiator": "agent"}']
        result = filter_lines(lines, "initiator")
        assert len(result) == 2

    def test_filter_lines_no_matches_returns_empty(self) -> None:
        """Filter with no matches returns an empty list."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["alpha", "beta", "gamma"]
        result = filter_lines(lines, "zzz")
        assert result == []
```

- [ ] Add the `TestFilterLines` class above to `tests/unit/tui/test_agent_logs_screen.py`

### Step 2: Run to confirm tests fail

```bash
python3 -m pytest tests/unit/tui/test_agent_logs_screen.py::TestFilterLines -v
```

Expected: 5 failures with `ImportError: cannot import name 'filter_lines'`

- [ ] Confirm 5 failures

### Step 3: Implement `filter_lines` in `agent_logs.py`

Add the following function after `read_new_lines` and before the `AgentLogsScreen` class in `breqy/tui/screens/agent_logs.py`:

```python
def filter_lines(lines: Iterable[str], filter_str: str) -> list[str]:
    """Return lines containing *filter_str* (case-insensitive).

    If *filter_str* is empty, all lines are returned.
    """
    if not filter_str:
        return list(lines)
    needle = filter_str.lower()
    return [line for line in lines if needle in line.lower()]
```

Also add `Iterable` to the imports at the top of the file:

```python
from collections.abc import Iterable
```

- [ ] Add `filter_lines` function to `agent_logs.py`
- [ ] Add `from collections.abc import Iterable` import

### Step 4: Run tests to confirm they pass

```bash
python3 -m pytest tests/unit/tui/test_agent_logs_screen.py::TestFilterLines -v
```

Expected: 5 passed

- [ ] Confirm 5 passed

### Step 5: Run full unit test suite to check for regressions

```bash
python3 -m pytest tests/unit/tui/ -v
```

Expected: all previously passing tests still pass, 5 new tests pass

- [ ] Confirm no regressions

### Step 6: Commit

```bash
git add tests/unit/tui/test_agent_logs_screen.py breqy/tui/screens/agent_logs.py
git commit -m "test(tui): add TestFilterLines; feat(tui): implement filter_lines pure helper"
```

- [ ] Commit

---

## Task 2: Integrate filter into `AgentLogsScreen` — full screen update

**Files:**
- Modify: `breqy/tui/screens/agent_logs.py`

This task has no net-new pure-logic tests (all logic flows through `filter_lines`, already tested). The screen-level wiring (Input widget, key bindings, on_mount/poll flow) is verified by running the existing TUI integration test suite after the change.

### Step 1: Update `agent_logs.py` — full replacement

Replace the entire content of `breqy/tui/screens/agent_logs.py` with the following:

```python
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

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
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

    BINDINGS = [
        Binding("escape", "pop_screen", "Close", show=True),
        Binding("q", "pop_screen", "Close", show=True),
        Binding("f", "focus_filter", "Filter", show=True),
        Binding("c", "clear_filter", "Clear filter", show=True),
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
        except Exception:
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
```

- [ ] Replace `breqy/tui/screens/agent_logs.py` with the content above

### Step 2: Run unit tests

```bash
python3 -m pytest tests/unit/tui/ -v
```

Expected: all 14 tests pass (9 existing + 5 new `filter_lines` tests)

- [ ] Confirm 14 passed

### Step 3: Run TUI integration tests that cover app and chat screen

```bash
python3 -m pytest tests/tui/test_app.py tests/tui/test_chat_screen.py tests/tui/test_commands.py -q
```

Expected: all pass (no regressions from the screen change)

- [ ] Confirm no regressions

### Step 4: Commit

```bash
git add breqy/tui/screens/agent_logs.py
git commit -m "feat(tui): add search/filter bar to AgentLogsScreen

- Add filter_lines() pure helper (case-insensitive substring match)
- Add _lines deque ring buffer (maxlen=1000) and _filter str to screen
- Update compose() to include Input#agent-logs-filter widget
- Update _load_initial_lines() to populate _lines then call _refresh_display()
- Update _poll_log(): extend _lines first; fast-path write when no filter,
  full _refresh_display() when filter is active
- Add _refresh_display(): clear + re-render filter_lines(_lines, _filter)
- Add _on_filter_changed handler (Input.Changed on #agent-logs-filter)
- Add action_focus_filter (f) and action_clear_filter (c) bindings
- Update docstring and module docstring"
```

- [ ] Commit

---

## Task 3: Update CHANGES.md

### Step 1: Add entry to the `### Added` section in `CHANGES.md`

Add this line in the `### Added` block:

```
- `AgentLogsScreen` now has a live-filtering search bar (`f` to focus, `c` to clear). Typing a substring instantly shows only matching lines from the ring buffer. A new `filter_lines(lines, filter_str)` pure helper handles case-insensitive filtering. `_lines: deque[str]` (maxlen=1000) buffers all lines since the screen opened; new lines from polls extend the buffer first before any display update.
```

- [ ] Add CHANGES.md entry

### Step 2: Commit

```bash
git add CHANGES.md
git commit -m "docs: update CHANGES.md for AgentLogsScreen search/filter"
```

- [ ] Commit

---

## Done

After Task 3 the feature is complete. The full changeset across all three commits:

| Commit | Scope |
|---|---|
| `test + feat: filter_lines` | Pure helper + 5 new unit tests |
| `feat: AgentLogsScreen filter bar` | Screen integration (Input, buffer, bindings) |
| `docs: CHANGES.md` | Changelog entry |

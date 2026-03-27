"""ToolPanel widget — displays tool invocations with status and output.

Tracks active and recently completed tool invocations in a side panel,
showing status icons, output chunks, summaries, and errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from textual.widget import Widget
from textual.widgets import RichLog

from breqy.domain.enums import ToolStatus
from breqy.tui.constants import TOOL_STATUS_ICONS


@dataclass
class _ToolEntry:
    """Internal tracking structure for a single tool invocation."""

    invocation_id: str
    tool_name: str
    status: ToolStatus = ToolStatus.RUNNING
    output_chunks: list[str] = field(default_factory=list)
    summary: str = ""
    error: str = ""


class ToolPanel(Widget):
    """Displays tool invocations with status icons and output."""

    MAX_TOOLS: int = 50

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._entries: dict[str, _ToolEntry] = {}
        self._order: list[str] = []

    def compose(self):  # noqa: ANN201
        yield RichLog(id="tool-log", wrap=True, markup=True)

    @property
    def log_widget(self) -> RichLog:
        """Return the inner RichLog widget."""
        return self.query_one("#tool-log", RichLog)

    def on_mount(self) -> None:
        """Render the empty state on mount."""
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def tool_started(self, invocation_id: str, tool_name: str, summary: str = "") -> None:
        """Add a new tool entry with RUNNING status."""
        entry = _ToolEntry(
            invocation_id=invocation_id,
            tool_name=tool_name,
            summary=summary,
        )
        self._entries[invocation_id] = entry
        self._order.append(invocation_id)
        self._enforce_max_tools()
        self._refresh_display()

    def tool_output(self, invocation_id: str, chunk: str) -> None:
        """Append an output chunk to a tracked tool."""
        entry = self._entries.get(invocation_id)
        if entry is None:
            return
        entry.output_chunks.append(chunk)
        self._refresh_display()

    def tool_completed(self, invocation_id: str, summary: str = "") -> None:
        """Mark a tool as COMPLETED with an optional summary."""
        entry = self._entries.get(invocation_id)
        if entry is None:
            return
        entry.status = ToolStatus.COMPLETED
        entry.summary = summary
        self._enforce_max_tools()
        self._refresh_display()

    def tool_failed(self, invocation_id: str, error: str = "") -> None:
        """Mark a tool as FAILED with an optional error message."""
        entry = self._entries.get(invocation_id)
        if entry is None:
            return
        entry.status = ToolStatus.FAILED
        entry.error = error
        self._refresh_display()

    def clear_tools(self) -> None:
        """Clear all tool entries."""
        self._entries.clear()
        self._order.clear()
        self._refresh_display()

    # ------------------------------------------------------------------ #
    # Internal rendering
    # ------------------------------------------------------------------ #

    def _enforce_max_tools(self) -> None:
        """Drop oldest completed tools when entry count exceeds MAX_TOOLS."""
        while len(self._entries) > self.MAX_TOOLS:
            # Find the oldest completed/failed entry to remove
            removed = False
            for inv_id in list(self._order):
                entry = self._entries.get(inv_id)
                if entry and entry.status in (ToolStatus.COMPLETED, ToolStatus.FAILED):
                    del self._entries[inv_id]
                    self._order.remove(inv_id)
                    removed = True
                    break
            if not removed:
                # If no completed/failed entries, drop the oldest entry
                oldest_id = self._order.pop(0)
                self._entries.pop(oldest_id, None)

    def _refresh_display(self) -> None:
        """Clear and re-render all tool entries to the RichLog."""
        log = self.log_widget
        log.clear()

        if not self._entries:
            log.write("[dim]No tools[/dim]")
            return

        for inv_id in self._order:
            entry = self._entries.get(inv_id)
            if entry is None:
                continue
            self._render_entry(log, entry)

    def _render_entry(self, log: RichLog, entry: _ToolEntry) -> None:
        """Render a single tool entry to the log."""
        icon = TOOL_STATUS_ICONS.get(entry.status, "\u25cb")
        log.write(f"{icon} {entry.tool_name}")

        for chunk in entry.output_chunks:
            for line in chunk.splitlines():
                log.write(f"[dim]  {line}[/dim]")

        if entry.summary:
            log.write(f"  \u2192 {entry.summary}")

        if entry.error:
            log.write(f"  [red]\u2717 {entry.error}[/red]")

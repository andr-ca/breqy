"""TaskPanel widget — displays task list with status icons.

Renders tasks in a ``RichLog`` with status-specific icons and optional
indentation for nested (child) tasks.  The full log is rewritten on every
update so that status changes are reflected immediately.
"""
from __future__ import annotations

from typing import TypedDict

from textual.widget import Widget
from textual.widgets import RichLog

from breqy.domain.enums import TaskStatus
from breqy.tui.constants import TASK_STATUS_ICONS


class _TaskEntry(TypedDict):
    """Internal representation of a task in the panel."""

    title: str
    status: TaskStatus
    parent_id: str | None


class TaskPanel(Widget):
    """Side-panel widget that lists tasks with status icons."""

    DEFAULT_CSS = """
    TaskPanel {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:  # type: ignore[override]
        super().__init__(**kwargs)
        self._tasks: dict[str, _TaskEntry] = {}

    def compose(self):  # noqa: ANN201
        yield RichLog(id="task-log", wrap=True, markup=True)

    @property
    def log_widget(self) -> RichLog:
        """Return the inner RichLog widget."""
        return self.query_one("#task-log", RichLog)

    def on_mount(self) -> None:
        """Render the empty state when the widget is first mounted."""
        self._rewrite_log()

    def update_task(
        self,
        task_id: str,
        title: str,
        status: TaskStatus,
        parent_id: str | None = None,
    ) -> None:
        """Add or update a task and re-render the list."""
        self._tasks[task_id] = _TaskEntry(
            title=title,
            status=status,
            parent_id=parent_id,
        )
        self._rewrite_log()

    def clear_tasks(self) -> None:
        """Remove all tasks and re-render (shows empty state)."""
        self._tasks.clear()
        self._rewrite_log()

    def _rewrite_log(self) -> None:
        """Clear the log and rewrite all task entries (or empty state)."""
        log = self.log_widget
        log.clear()

        if not self._tasks:
            log.write("[dim]No tasks[/dim]")
            return

        for entry in self._tasks.values():
            icon = TASK_STATUS_ICONS.get(entry["status"], "?")
            indent = "  " if entry["parent_id"] is not None else ""
            log.write(f"{indent}{icon} {entry['title']}")

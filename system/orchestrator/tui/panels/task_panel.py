# system/orchestrator/tui/panels/task_panel.py
from __future__ import annotations

import contextlib

from textual.widget import Widget
from textual.widgets import Static

from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.state_machine import Task


class TaskPanel(Widget):
    def __init__(self, tasks: list[tuple[Task, TaskEnvelope]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._tasks = {t.task_id: (t, env) for t, env in tasks}
        self._active_id: str | None = tasks[0][0].task_id if tasks else None

    def compose(self):
        yield Static("No active task", id="task-info")

    def handle_event(self, event: OrchestratorEvent) -> None:
        self._active_id = event.task_id
        task, env = self._tasks.get(event.task_id, (None, None))
        if task and env:
            info = (
                f"ID:     {env.task_id}\n"
                f"Title:  {env.title}\n"
                f"Type:   {env.task_type} / {env.component}\n"
                f"State:  {event.to_state or task.state.value}\n"
                f"Role:   {event.role or '—'}\n"
                f"Agent:  {event.agent_type or '—'}\n"
                f"Rework: {task.rework_count} / 3\n"
                f"Branch: {task.branch or '—'}\n"
                f"PR:     {task.pr_url or '—'}"
            )
            with contextlib.suppress(Exception):
                self.query_one("#task-info", Static).update(info)

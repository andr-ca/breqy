"""TaskLoader — abstract base class for task loading strategies."""
from __future__ import annotations
from abc import ABC, abstractmethod
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class TaskLoader(ABC):
    """Abstract interface for loading pending tasks from any source."""

    @abstractmethod
    def load_pending(self) -> list[TaskEnvelope]: ...


class CompositeTaskLoader(TaskLoader):
    """GitHub Issues primary; local YAML fallback. GitHub wins on same task_id."""

    def __init__(self, github: "TaskLoader", local: "TaskLoader") -> None:
        self._github = github
        self._local = local

    def load_pending(self) -> list[TaskEnvelope]:
        github_tasks = self._github.load_pending()
        github_ids = {t.task_id for t in github_tasks}
        local_tasks = [t for t in self._local.load_pending() if t.task_id not in github_ids]
        return github_tasks + local_tasks

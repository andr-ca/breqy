from __future__ import annotations

from abc import ABC, abstractmethod

from system.orchestrator.schemas.task_envelope import TaskEnvelope


class TaskLoader(ABC):
    @abstractmethod
    def load_pending(self) -> list[TaskEnvelope]: ...

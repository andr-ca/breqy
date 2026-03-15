from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.task_loader import TaskLoader


class LocalYamlTaskLoader(TaskLoader):
    def __init__(self, tasks_dir: Path) -> None:
        self._dir = tasks_dir

    def load_pending(self) -> list[TaskEnvelope]:
        tasks: list[TaskEnvelope] = []
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text())
                tasks.append(TaskEnvelope.model_validate(data))
            except (yaml.YAMLError, ValidationError):
                pass   # skip malformed files
        return tasks

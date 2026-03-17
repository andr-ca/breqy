"""LocalYamlTaskLoader — loads tasks from a directory of YAML files."""
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import ValidationError
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class LocalYamlTaskLoader(TaskLoader):
    """Loads TaskEnvelope objects from *.yaml files in a local directory."""

    def __init__(self, tasks_dir: Path) -> None:
        self._dir = tasks_dir

    def load_pending(self) -> list[TaskEnvelope]:
        """Return all valid TaskEnvelopes found in the tasks directory."""
        tasks: list[TaskEnvelope] = []
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text())
                tasks.append(TaskEnvelope.model_validate(data))
            except (yaml.YAMLError, ValidationError):
                pass
        return tasks

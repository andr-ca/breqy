"""ArtifactStore — read/write task artifacts under base/<task_id>/."""
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ArtifactStore:
    """Read/write task artifacts under base/<task_id>/. Pydantic → .json, str → .md."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def _path(self, task_id: str, name: str, suffix: str) -> Path:
        d = self._base / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{name}{suffix}"

    def write(self, task_id: str, name: str, content: BaseModel | str) -> Path:
        if isinstance(content, BaseModel):
            p = self._path(task_id, name, ".json")
            p.write_text(content.model_dump_json(indent=2))
        else:
            p = self._path(task_id, name, ".md")
            p.write_text(content)
        return p

    def read(self, task_id: str, name: str, model: type[T]) -> T | None:
        p = self._base / task_id / f"{name}.json"
        if not p.exists():
            return None
        return model.model_validate_json(p.read_text())

    def read_text(self, task_id: str, name: str) -> str | None:
        p = self._base / task_id / f"{name}.md"
        if not p.exists():
            return None
        return p.read_text()

    def exists(self, task_id: str, name: str) -> bool:
        base = self._base / task_id / name
        return base.with_suffix(".json").exists() or base.with_suffix(".md").exists()

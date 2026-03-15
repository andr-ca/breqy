from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TaskType = Literal["feature", "bug", "refactor", "hotfix"]


class TaskEnvelope(BaseModel):
    task_id: str
    title: str
    description: str = ""
    task_type: TaskType
    component: str
    dependencies: list[str] = []
    acceptance_criteria: list[str] = []
    test_hints: list[str] = []
    priority: str = "medium"
    labels: list[str] = []
    github_issue_number: int | None = None

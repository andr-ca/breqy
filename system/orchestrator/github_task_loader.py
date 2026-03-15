from __future__ import annotations

import json
import re
import subprocess

import yaml
from pydantic import ValidationError

from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.task_loader import TaskLoader

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


class GitHubTaskLoader(TaskLoader):
    def __init__(self, repo: str, managed_label: str = "orchestrator:managed") -> None:
        self._repo = repo
        self._label = managed_label

    def load_pending(self) -> list[TaskEnvelope]:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", self._repo,
             "--label", self._label,
             "--json", "number,title,body,labels"],
            capture_output=True, text=True,
        )
        issues = json.loads(result.stdout or "[]")
        tasks: list[TaskEnvelope] = []
        for issue in issues:
            task = self._parse_issue(issue)
            if task:
                tasks.append(task)
        return tasks

    def _parse_issue(self, issue: dict) -> TaskEnvelope | None:
        body = issue.get("body") or ""
        match = _YAML_BLOCK_RE.search(body)
        if not match:
            return None
        try:
            data = yaml.safe_load(match.group(1))
            data["github_issue_number"] = issue["number"]
            return TaskEnvelope.model_validate(data)
        except (yaml.YAMLError, ValidationError):
            return None

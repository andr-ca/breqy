"""GitHubTaskLoader — loads tasks from GitHub Issues with orchestrator:managed label."""
from __future__ import annotations
import json
import re
import subprocess
import yaml
from pydantic import ValidationError
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.schemas.task_envelope import TaskEnvelope

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


class GitHubTaskLoader(TaskLoader):
    """Loads TaskEnvelope objects from GitHub Issues containing a YAML code block."""

    def __init__(self, repo: str, managed_label: str = "orchestrator:managed") -> None:
        self._repo = repo
        self._label = managed_label

    def load_pending(self) -> list[TaskEnvelope]:
        """Fetch all managed issues and parse TaskEnvelopes from their YAML blocks."""
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", self._repo,
             "--label", self._label,
             "--json", "number,title,body,labels"],
            capture_output=True, text=True,
        )
        issues = json.loads(result.stdout or "[]")
        return [t for t in (self._parse_issue(i) for i in issues) if t is not None]

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

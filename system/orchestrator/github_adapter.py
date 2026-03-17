"""GitHubAdapter — issue label management and PR operations via gh CLI."""
from __future__ import annotations
import json
import subprocess
from pydantic import BaseModel


class PrStatus(BaseModel):
    state: str
    mergeable: str = ""
    url: str = ""


class GitHubAdapter:
    """Thin wrapper around the gh CLI for issue labels and PR management."""

    def __init__(self, repo: str) -> None:
        self._repo = repo

    def _run(self, *args: str) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        result.check_returncode()
        return result.stdout.strip()

    def set_task_state(self, issue_number: int, new_state: str, old_state: str | None = None) -> None:
        """Update the state label on a GitHub issue."""
        if old_state:
            self._run(
                "gh", "issue", "edit", str(issue_number),
                "--repo", self._repo,
                "--remove-label", f"state:{old_state}",
            )
        self._run(
            "gh", "issue", "edit", str(issue_number),
            "--repo", self._repo,
            "--add-label", f"state:{new_state}",
        )

    def get_task_state(self, issue_number: int) -> str | None:
        """Return the current state label value, or None if no state label found."""
        out = self._run(
            "gh", "issue", "view", str(issue_number),
            "--repo", self._repo,
            "--json", "labels",
        )
        labels = json.loads(out).get("labels", [])
        for lbl in labels:
            name = lbl.get("name", "")
            if name.startswith("state:"):
                return name[len("state:"):]
        return None

    def create_pr(self, branch: str, title: str, body: str) -> str:
        """Create a PR and return its URL."""
        return self._run(
            "gh", "pr", "create",
            "--repo", self._repo,
            "--head", branch,
            "--title", title,
            "--body", body,
        )

    def get_pr_status(self, pr_url: str) -> PrStatus:
        """Fetch current PR state and mergeability."""
        out = self._run("gh", "pr", "view", pr_url, "--json", "state,mergeable,url")
        data = json.loads(out)
        return PrStatus.model_validate(data)

    def pr_is_merged(self, pr_url: str) -> bool:
        """Return True if the PR has been merged."""
        return self.get_pr_status(pr_url).state == "MERGED"

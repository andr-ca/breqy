from __future__ import annotations

import json
import subprocess

from pydantic import BaseModel


class PrStatus(BaseModel):
    state: str
    mergeable: str = ""
    url: str = ""


class GitHubAdapter:
    def __init__(self, repo: str) -> None:
        self._repo = repo

    def _run(self, *args: str) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        result.check_returncode()
        return result.stdout.strip()

    def set_task_state(
        self, issue_number: int, new_state: str, old_state: str | None = None
    ) -> None:
        """Swap state labels. Remove old_state label (if given) then add new_state label."""
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
        """Read the current state:* label from the issue. Returns raw state string or None."""
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
        return self._run(
            "gh", "pr", "create",
            "--repo", self._repo,
            "--head", branch,
            "--title", title,
            "--body", body,
        )

    def get_pr_status(self, pr_url: str) -> PrStatus:
        out = self._run("gh", "pr", "view", pr_url, "--json", "state,mergeable,url")
        data = json.loads(out)
        return PrStatus.model_validate(data)

    def pr_is_merged(self, pr_url: str) -> bool:
        status = self.get_pr_status(pr_url)
        return status.state == "MERGED"

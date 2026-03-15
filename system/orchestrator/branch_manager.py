from __future__ import annotations
import re
import subprocess
from pathlib import Path


_PREFIXES = {
    "feature": "feat",
    "feat": "feat",
    "bug": "fix",
    "fix": "fix",
    "refactor": "refactor",
    "hotfix": "hotfix",
}

_MERGE_TARGETS = {
    "hotfix": "main",
}


class BranchError(Exception):
    pass


class BranchManager:
    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            args, cwd=self._root, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise BranchError(f"git {args} failed: {result.stderr.strip()}")
        return result

    def _make_branch_name(self, task_id: str, task_type: str, slug: str) -> str:
        prefix = _PREFIXES.get(task_type, "feat")
        return f"{prefix}/{task_id}-{slug}"

    @staticmethod
    def make_slug(title: str) -> str:
        """Convert a raw title string into a kebab-case slug (max 40 chars)."""
        return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]

    def create_branch(self, task_id: str, task_type: str, slug: str) -> str:
        """Create branch. Caller provides pre-slugified slug (use make_slug())."""
        name = self._make_branch_name(task_id, task_type, slug)
        self._run("git", "checkout", "-b", name)
        return name

    def branch_exists(self, name: str) -> bool:
        result = self._run(
            "git", "rev-parse", "--verify", f"refs/heads/{name}", check=False
        )
        return result.returncode == 0

    def is_stale(self, name: str, max_age_days: int) -> bool:
        result = self._run(
            "git", "log", "-1", "--format=%ct", f"refs/heads/{name}", check=False
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        import time
        age_secs = time.time() - int(result.stdout.strip())
        return age_secs > max_age_days * 86400

    def rebase(self, name: str, onto: str) -> None:
        self._run("git", "rebase", onto, name)

    def merge_target(self, task_type: str) -> str:
        return _MERGE_TARGETS.get(task_type, "dev")

    def current_branch(self) -> str:
        return self._run("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def push(self, name: str) -> None:
        self._run("git", "push", "--set-upstream", "origin", name)

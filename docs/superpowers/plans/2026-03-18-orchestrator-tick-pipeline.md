# Orchestrator `_tick()` Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `OrchestratorLoop._tick()` to drive tasks through all 17 states — planner → branch → test-case design → doer → checker → tester → QA → CI gate → lessons → auto-merge — with rework loops (max 3), retries (max 3), and BLOCKED escalation.

**Architecture:** Per-state handler methods dispatched via `_HANDLERS: dict[TaskState, str]` in `orchestrator.py`. A shared `_run_agent(task, env, role, prior_artifacts)` helper handles all runner/adapter invocations. New `start()` method on `AgentRunner` ABC returns `Popen` for process tracking; `run()` becomes a thin wrapper. `CIAdapter` and `GitHubAdapter` are injected as optional constructor params.

**Tech Stack:** Python 3.12, Pydantic v2, subprocess, pytest, unittest.mock. `gh` CLI for GitHub operations. No new files — all changes in existing modules.

---

## File Map

| Action | File |
|---|---|
| Modify | `system/orchestrator/runners/base.py` |
| Modify | `system/orchestrator/runners/claude_runner.py` |
| Modify | `system/orchestrator/runners/codex_runner.py` |
| Modify | `system/orchestrator/runners/gemini_runner.py` |
| Modify | `system/orchestrator/runners/copilot_runner.py` |
| Modify | `system/orchestrator/runners/qwen_runner.py` |
| Modify | `system/orchestrator/branch_manager.py` |
| Modify | `system/orchestrator/github_adapter.py` |
| Modify | `system/orchestrator/orchestrator.py` |
| Modify | `system/orchestrator/main.py` |
| Modify | `tests/unit/orchestrator/runners/test_runners_base.py` |
| Modify | `tests/unit/orchestrator/runners/test_claude_runner.py` |
| Modify | `tests/unit/orchestrator/runners/test_other_runners.py` |
| Modify | `tests/unit/orchestrator/test_branch_manager.py` |
| Modify | `tests/unit/orchestrator/test_github_adapter.py` |
| Modify | `tests/unit/orchestrator/test_orchestrator_loop.py` |

---

### Task 1: AgentRunner.start() — ABC + ClaudeRunner

**Files:**
- Modify: `system/orchestrator/runners/base.py`
- Modify: `system/orchestrator/runners/claude_runner.py`
- Modify: `tests/unit/orchestrator/runners/test_runners_base.py`
- Modify: `tests/unit/orchestrator/runners/test_claude_runner.py`

The orchestrator's `_run_agent` needs a `Popen` object to store as `_current_process` for the kill path. Currently `run()` blocks immediately — there's no way to get the `Popen`. Solution: add `start()` as the single abstract method; `run()` becomes a concrete default on the ABC that calls `start()` + `communicate()`. `ClaudeRunner` overrides `run()` to keep rate-limit detection.

**Context to read first:** `system/orchestrator/runners/base.py`, `system/orchestrator/runners/claude_runner.py`, `tests/unit/orchestrator/runners/test_runners_base.py`, `tests/unit/orchestrator/runners/test_claude_runner.py`

- [ ] **Step 1: Write failing test for start() in test_runners_base.py**

Add to `tests/unit/orchestrator/runners/test_runners_base.py`:

```python
import subprocess
from system.orchestrator.schemas.run_result import RunContext, RunResult
from pathlib import Path


def test_start_is_abstract():
    """A subclass that only implements run() (not start()) cannot be instantiated."""
    class OnlyRunRunner(AgentRunner):
        def run(self, prompt: str, context: RunContext) -> RunResult:
            return RunResult(status="completed", output="", exit_code=0)
    with pytest.raises(TypeError):
        OnlyRunRunner()


def test_abc_run_default_calls_start_and_communicate():
    """The ABC's default run() calls start() then communicate()."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("hello", None)
    mock_proc.returncode = 0

    class MinimalRunner(AgentRunner):
        def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
            return mock_proc

    runner = MinimalRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hi", ctx)
    assert result.status == "completed"
    assert result.output == "hello"
    mock_proc.communicate.assert_called_once()
```

Also add `from unittest.mock import MagicMock` to imports.

Note: `test_runner_interface` also needs updating since `run()` will no longer be abstract. Update it to implement `start()` instead:

```python
def test_runner_interface():
    class MyRunner(AgentRunner):
        def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
            return MagicMock(communicate=lambda: ("ok", None), returncode=0)

    runner = MyRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hello", ctx)
    assert result.status == "completed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/runners/test_runners_base.py -v
```
Expected: `test_start_is_abstract` FAILS (`OnlyRunRunner` can be instantiated because `run()` is currently the only abstract method — it IS implemented, so no TypeError is raised).

- [ ] **Step 3: Update AgentRunner ABC**

Replace contents of `system/orchestrator/runners/base.py`:

```python
from __future__ import annotations
import subprocess
from abc import ABC, abstractmethod
from system.orchestrator.schemas.run_result import RunContext, RunResult


class AgentRunner(ABC):
    @abstractmethod
    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        """Start the agent subprocess and return without waiting."""
        ...

    def run(self, prompt: str, context: RunContext) -> RunResult:
        """Default implementation: start() + communicate(). Override for custom logic."""
        proc = self.start(prompt, context)
        output, _ = proc.communicate()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

- [ ] **Step 4: Write failing test for ClaudeRunner.start()**

Add to `tests/unit/orchestrator/runners/test_claude_runner.py`:

```python
def test_claude_runner_start_returns_popen(ctx):
    """start() creates a subprocess and returns Popen without blocking."""
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        runner = ClaudeRunner()
        proc = runner.start("do the thing", ctx)
    mock_popen.assert_called_once()
    assert proc is mock_popen.return_value


def test_claude_runner_start_passes_session_id(ctx):
    ctx_with_session = ctx.model_copy(update={"session_id": "sess-abc"})
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        ClaudeRunner().start("prompt", ctx_with_session)
    cmd = mock_popen.call_args[0][0]
    assert "--resume" in cmd
    assert "sess-abc" in cmd
```

Also update the existing `_proc()` helper and tests. Currently `_proc()` sets `m.stdout = iter(...)` for line iteration; after the refactor `run()` calls `communicate()`, so change `_proc` to:

```python
def _proc(stdout="", returncode=0):
    m = MagicMock()
    m.communicate.return_value = (stdout, None)
    m.returncode = returncode
    return m
```

Update all existing tests that patch `subprocess.Popen` to use `patch.object(ClaudeRunner, "start", return_value=_proc(...))` OR keep patching `subprocess.Popen` with the new `_proc()`. Keeping `subprocess.Popen` patch is simpler — the existing tests still work because `start()` calls `subprocess.Popen`, and `run()` now calls `communicate()` on the returned mock.

- [ ] **Step 5: Run tests to see new start() tests fail**

```bash
pytest tests/unit/orchestrator/runners/test_claude_runner.py::test_claude_runner_start_returns_popen -v
```
Expected: FAIL — `ClaudeRunner` has no `start()` method.

- [ ] **Step 6: Implement start() and refactor run() in ClaudeRunner**

Replace `system/orchestrator/runners/claude_runner.py`:

```python
from __future__ import annotations
import subprocess
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.session_manager import is_rate_limit_output

_PROVIDER_NAME = "claude"
_ENV_KEY = "ANTHROPIC_API_KEY"


class ClaudeRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if context.session_id:
            cmd += ["--resume", context.session_id]
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=self._env(context),
        )

    def run(self, prompt: str, context: RunContext) -> RunResult:
        proc = self.start(prompt, context)
        output, _ = proc.communicate()
        if is_rate_limit_output(output):
            return RunResult(status="rate_limited", output=output, exit_code=proc.returncode)
        if proc.returncode != 0:
            return RunResult(status="failed", output=output, exit_code=proc.returncode)
        return RunResult(status="completed", output=output, exit_code=0)

    def _env(self, context: RunContext) -> dict[str, str]:
        import os
        env = os.environ.copy()
        env.update(context.extra_env)
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return env
```

- [ ] **Step 7: Run all runner tests**

```bash
pytest tests/unit/orchestrator/runners/ -v
```
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add system/orchestrator/runners/base.py system/orchestrator/runners/claude_runner.py \
    tests/unit/orchestrator/runners/test_runners_base.py \
    tests/unit/orchestrator/runners/test_claude_runner.py
git commit -m "feat(runners): add start() to AgentRunner ABC; refactor ClaudeRunner.run() as thin wrapper"
```

---

### Task 2: AgentRunner.start() — Codex, Gemini, Copilot, Qwen

**Files:**
- Modify: `system/orchestrator/runners/codex_runner.py`
- Modify: `system/orchestrator/runners/gemini_runner.py`
- Modify: `system/orchestrator/runners/copilot_runner.py`
- Modify: `system/orchestrator/runners/qwen_runner.py`
- Modify: `tests/unit/orchestrator/runners/test_other_runners.py`

All 4 runners share the same pattern: `Popen`, then `raw.read()`. After Task 1 the ABC provides a default `run()` that calls `start()` + `communicate()`, so these runners only need to implement `start()` and can delete `run()`.

**Context to read first:** `system/orchestrator/runners/codex_runner.py`, `system/orchestrator/runners/gemini_runner.py`, `system/orchestrator/runners/copilot_runner.py`, `system/orchestrator/runners/qwen_runner.py`, `tests/unit/orchestrator/runners/test_other_runners.py`

- [ ] **Step 1: Write failing tests for start() on all 4 runners**

Add to `tests/unit/orchestrator/runners/test_other_runners.py`:

```python
@pytest.mark.parametrize("RunnerCls,expected_cmd_token", [
    (CodexRunner, "codex"),
    (GeminiRunner, "gemini"),
    (CopilotRunner, "gh"),
    (QwenRunner, "qwen"),
])
def test_runner_start_returns_popen(RunnerCls, expected_cmd_token, ctx):
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        runner = RunnerCls()
        proc = runner.start("check this code", ctx)
    cmd = mock_popen.call_args[0][0]
    assert expected_cmd_token in cmd
    assert proc is mock_popen.return_value
```

Also update the existing `_proc()` helper to use `communicate.return_value`:

```python
def _proc(stdout="done\n", returncode=0):
    m = MagicMock()
    m.communicate.return_value = (stdout, None)
    m.returncode = returncode
    return m
```

- [ ] **Step 2: Run tests to verify new tests fail**

```bash
pytest tests/unit/orchestrator/runners/test_other_runners.py::test_runner_start_returns_popen -v
```
Expected: FAIL — none of the 4 runners has `start()`.

- [ ] **Step 3: Implement start() in all 4 runners (remove run())**

**`system/orchestrator/runners/codex_runner.py`** — replace entire file:

```python
from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "codex"
_ENV_KEY = "OPENAI_API_KEY"


class CodexRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["codex", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
```

**`system/orchestrator/runners/gemini_runner.py`** — replace entire file:

```python
from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "gemini"
_ENV_KEY = "GOOGLE_API_KEY"


class GeminiRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["gemini", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
```

**`system/orchestrator/runners/copilot_runner.py`** — replace entire file:

```python
from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "copilot"
_ENV_KEY = "GITHUB_COPILOT_TOKEN"


class CopilotRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["gh", "copilot", "suggest", prompt],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
```

**`system/orchestrator/runners/qwen_runner.py`** — replace entire file:

```python
from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "qwen"
_ENV_KEY = "DASHSCOPE_API_KEY"


class QwenRunner(AgentRunner):
    """Qwen runner. Requires DASHSCOPE_API_KEY in environment."""

    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["qwen", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
```

- [ ] **Step 4: Run all runner tests**

```bash
pytest tests/unit/orchestrator/runners/ -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/runners/codex_runner.py \
    system/orchestrator/runners/gemini_runner.py \
    system/orchestrator/runners/copilot_runner.py \
    system/orchestrator/runners/qwen_runner.py \
    tests/unit/orchestrator/runners/test_other_runners.py
git commit -m "feat(runners): implement start() on Codex/Gemini/Copilot/Qwen; inherit ABC default run()"
```

---

### Task 3: BranchManager.diff()

**Files:**
- Modify: `system/orchestrator/branch_manager.py`
- Modify: `tests/unit/orchestrator/test_branch_manager.py`

**Context to read first:** `system/orchestrator/branch_manager.py`, `tests/unit/orchestrator/test_branch_manager.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_branch_manager.py`:

```python
def test_diff_calls_git_diff_three_dot(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="diff content", stderr="")
        result = bm.diff("feat/BRQ-1-test", "dev")
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ("git", "diff", "dev...feat/BRQ-1-test") in calls
    assert result == "diff content"


def test_diff_returns_empty_string_when_no_diff(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = bm.diff("feat/BRQ-1-test", "dev")
    assert result == ""


def test_diff_does_not_raise_on_nonzero_exit(bm):
    """check=False means a non-zero exit (e.g. unknown branch) does not raise."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="unknown ref")
        result = bm.diff("no-such-branch", "dev")
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_branch_manager.py::test_diff_calls_git_diff_three_dot -v
```
Expected: FAIL — `BranchManager` has no `diff()` method.

- [ ] **Step 3: Implement diff()**

Add to `system/orchestrator/branch_manager.py` after `delete_branch`:

```python
def diff(self, branch: str, base: str) -> str:
    """Return git diff between base and branch tip (three-dot merge-base diff)."""
    result = self._run("git", "diff", f"{base}...{branch}", check=False)
    return result.stdout
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/orchestrator/test_branch_manager.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/branch_manager.py tests/unit/orchestrator/test_branch_manager.py
git commit -m "feat(branch-manager): add diff(branch, base) for checker context"
```

---

### Task 4: GitHubAdapter — merge_pr() + create_pr() base parameter

**Files:**
- Modify: `system/orchestrator/github_adapter.py`
- Modify: `tests/unit/orchestrator/test_github_adapter.py`

**Context to read first:** `system/orchestrator/github_adapter.py`, `tests/unit/orchestrator/test_github_adapter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_github_adapter.py`:

```python
def test_merge_pr_calls_gh_squash(gh):
    with patch("subprocess.run", return_value=_run_ok()) as mock_run:
        gh.merge_pr("https://github.com/owner/repo/pull/5")
    cmd = mock_run.call_args[0][0]
    assert "gh" in cmd
    assert "merge" in cmd
    assert "--squash" in cmd
    assert "--delete-branch" in cmd
    assert "https://github.com/owner/repo/pull/5" in cmd


def test_merge_pr_raises_on_failure(gh):
    with patch("subprocess.run", return_value=_run_ok(returncode=1)):
        with pytest.raises(Exception):
            gh.merge_pr("https://github.com/owner/repo/pull/5")


def test_create_pr_passes_base_to_gh(gh):
    pr_url = "https://github.com/owner/repo/pull/6"
    with patch("subprocess.run", return_value=_run_ok(stdout=pr_url)) as mock_run:
        url = gh.create_pr("feat/BRQ-1-test", "dev", "My PR", "Body text")
    cmd = mock_run.call_args[0][0]
    assert "--base" in cmd
    idx = cmd.index("--base")
    assert cmd[idx + 1] == "dev"
    assert url == pr_url
```

Also update `test_create_pr_returns_url` — the call signature now requires `base`:

```python
def test_create_pr_returns_url(gh):
    pr_url = "https://github.com/owner/repo/pull/5"
    with patch("subprocess.run", return_value=_run_ok(stdout=pr_url)):
        url = gh.create_pr("feat/BRQ-1-test", "dev", "My PR", "Body text")
        assert url == pr_url.strip()
```

- [ ] **Step 2: Run tests to verify new tests fail**

```bash
pytest tests/unit/orchestrator/test_github_adapter.py::test_merge_pr_calls_gh_squash \
    tests/unit/orchestrator/test_github_adapter.py::test_create_pr_passes_base_to_gh -v
```
Expected: FAIL.

- [ ] **Step 3: Implement merge_pr() and update create_pr()**

Replace `system/orchestrator/github_adapter.py`:

```python
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

    def create_pr(self, branch: str, base: str, title: str, body: str) -> str:
        """Create a PR against base and return its URL."""
        return self._run(
            "gh", "pr", "create",
            "--repo", self._repo,
            "--head", branch,
            "--base", base,
            "--title", title,
            "--body", body,
        )

    def merge_pr(self, pr_url: str) -> None:
        """Squash-merge a PR and delete its branch. Raises on non-zero exit."""
        self._run("gh", "pr", "merge", pr_url, "--squash", "--delete-branch")

    def get_pr_status(self, pr_url: str) -> PrStatus:
        """Fetch current PR state and mergeability."""
        out = self._run("gh", "pr", "view", pr_url, "--json", "state,mergeable,url")
        data = json.loads(out)
        return PrStatus.model_validate(data)

    def pr_is_merged(self, pr_url: str) -> bool:
        """Return True if the PR has been merged."""
        return self.get_pr_status(pr_url).state == "MERGED"
```

- [ ] **Step 4: Run all GitHub adapter tests**

```bash
pytest tests/unit/orchestrator/test_github_adapter.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/github_adapter.py tests/unit/orchestrator/test_github_adapter.py
git commit -m "feat(github-adapter): add merge_pr(); add base param to create_pr()"
```

---

### Task 5: OrchestratorLoop — wire ci_adapter + github_adapter; update main.py

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `system/orchestrator/main.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/main.py`, `tests/unit/orchestrator/test_orchestrator_loop.py`, `system/orchestrator/ci_adapter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.github_adapter import GitHubAdapter


def _make_loop(tmp_path, ci_adapter=None, github_adapter=None, branch_manager=None):
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude", "checker": "codex"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()
    return OrchestratorLoop(
        config=cfg, state_machine=sm, artifact_store=store,
        event_log=log, event_queue=eq,
        ci_adapter=ci_adapter,
        github_adapter=github_adapter,
        branch_manager=branch_manager,
    )


def test_loop_stores_ci_adapter(tmp_path):
    mock_ci = MagicMock(spec=CIAdapter)
    loop = _make_loop(tmp_path, ci_adapter=mock_ci)
    assert loop._ci_adapter is mock_ci


def test_loop_stores_github_adapter(tmp_path):
    mock_gh = MagicMock(spec=GitHubAdapter)
    loop = _make_loop(tmp_path, github_adapter=mock_gh)
    assert loop._github_adapter is mock_gh


def test_loop_ci_adapter_defaults_to_none(tmp_path):
    loop = _make_loop(tmp_path)
    assert loop._ci_adapter is None


def test_loop_github_adapter_defaults_to_none(tmp_path):
    loop = _make_loop(tmp_path)
    assert loop._github_adapter is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_loop_stores_ci_adapter -v
```
Expected: FAIL — `OrchestratorLoop.__init__` has no `ci_adapter` parameter.

- [ ] **Step 3: Add ci_adapter and github_adapter to OrchestratorLoop.__init__**

In `system/orchestrator/orchestrator.py`, add two imports at the top:

```python
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.github_adapter import GitHubAdapter
```

Update `__init__` signature (add two optional params after `branch_manager`):

```python
def __init__(
    self,
    config: OrchestratorConfig,
    state_machine: ConcreteStateMachine,
    artifact_store: ArtifactStore,
    event_log: EventLog,
    event_queue: queue.Queue,
    credential_store: CredentialStore | None = None,
    loader: TaskLoader | None = None,
    branch_manager: BranchManager | None = None,
    ci_adapter: CIAdapter | None = None,
    github_adapter: GitHubAdapter | None = None,
) -> None:
    ...
    self._ci_adapter = ci_adapter
    self._github_adapter = github_adapter
```

Add the two assignment lines inside `__init__` (after the existing `self._branch_manager = branch_manager` line).

- [ ] **Step 4: Update main.py to wire CIAdapter and GitHubAdapter**

In `system/orchestrator/main.py`, add imports:

```python
from system.orchestrator.ci_adapter import CIAdapter
from system.orchestrator.github_adapter import GitHubAdapter
```

In `_run_orchestrator`, update the second `OrchestratorLoop` constructor call:

```python
loop = OrchestratorLoop(
    config=cfg,
    state_machine=loop._sm,
    artifact_store=loop._artifact_store,
    event_log=loop._log,
    event_queue=eq,
    loader=composite,
    branch_manager=BranchManager(repo_root=Path.cwd()),
    ci_adapter=CIAdapter(repo=cfg.github.repo),
    github_adapter=GitHubAdapter(repo=cfg.github.repo),
)
```

- [ ] **Step 5: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/orchestrator.py system/orchestrator/main.py \
    tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): wire ci_adapter and github_adapter constructor params"
```

---

### Task 6: _run_agent shared helper

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

This is the core shared helper used by all agent-invoking handlers. It resolves runner + adapter via `Router`, builds `TaskContext`, calls `runner.start()`, stores result via `ArtifactStore`, emits events. `prior_artifacts` dict values are **string content** (not file paths).

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/agent_adapters/base.py`, `system/orchestrator/schemas/run_result.py`, `system/orchestrator/schemas/artifacts.py`, `system/orchestrator/schemas/events.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
def test_run_agent_stores_artifact_and_emits_events(tmp_path):
    loop = _make_loop(tmp_path)

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": "done"}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[], notes="done")

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")

    output = loop._run_agent(task, env, "planner")

    assert output.status == "pass"
    # artifact written
    from system.orchestrator.schemas.artifacts import ParsedOutput as PO
    stored = loop._artifact_store.read("BRQ-1", "planner", PO)
    assert stored is not None
    assert stored.status == "pass"
    # events emitted
    events = []
    while not loop._queue.empty():
        events.append(loop._queue.get_nowait())
    event_types = [e.event_type for e in events]
    assert "agent_spawn" in event_types
    assert "agent_complete" in event_types


def test_run_agent_clears_process_tracking_after_run(tmp_path):
    loop = _make_loop(tmp_path)

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": ""}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[])

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._run_agent(task, env, "planner")

    assert loop._current_process is None
    assert loop._current_task_id is None


def test_run_agent_clears_tracking_on_exception(tmp_path):
    loop = _make_loop(tmp_path)

    mock_runner = MagicMock()
    mock_runner.start.side_effect = RuntimeError("spawn failed")
    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")

    with pytest.raises(RuntimeError):
        loop._run_agent(task, env, "planner")

    assert loop._current_process is None
    assert loop._current_task_id is None


def test_run_agent_extracts_failure_notes_from_prior_artifacts(tmp_path):
    """failure_notes key is removed from prior_artifacts and placed in TaskContext.failure_notes."""
    loop = _make_loop(tmp_path)

    captured_context: list = []

    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": ""}', None)
    mock_proc.returncode = 0

    mock_runner = MagicMock()
    mock_runner.start.return_value = mock_proc
    mock_adapter = MagicMock()

    def capture_prompt(env, context):
        captured_context.append(context)
        return "prompt"

    mock_adapter.build_prompt.side_effect = capture_prompt
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_adapter.parse_output.return_value = ParsedOutput(status="pass", artifact_paths=[])

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    prior = {"failure_notes": "checker said X", "some_key": "some_val"}

    loop._run_agent(task, env, "doer", prior_artifacts=prior)

    ctx = captured_context[0]
    assert ctx.failure_notes == "checker said X"
    assert "failure_notes" not in ctx.prior_artifacts
    assert "some_key" in ctx.prior_artifacts
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_run_agent_stores_artifact_and_emits_events -v
```
Expected: FAIL — `OrchestratorLoop` has no `_run_agent` method.

- [ ] **Step 3: Implement _run_agent in orchestrator.py**

Add imports at top of `system/orchestrator/orchestrator.py`:

```python
from system.orchestrator.agent_adapters.base import TaskContext
from system.orchestrator.schemas.artifacts import ParsedOutput
```

Add the method to `OrchestratorLoop` (after `_emit`):

```python
def _run_agent(
    self,
    task: Task,
    env: TaskEnvelope,
    role: str,
    prior_artifacts: dict[str, str] | None = None,
) -> ParsedOutput:
    runner, adapter = self._router.resolve(env.task_type, env.component, role)
    prior = dict(prior_artifacts) if prior_artifacts else {}
    failure_notes = prior.pop("failure_notes", "")
    context = TaskContext(
        task=env,
        prior_artifacts=prior,
        rework_count=task.rework_count,
        failure_notes=failure_notes,
    )
    prompt = adapter.build_prompt(env, context)
    run_context = RunContext(
        task_id=task.task_id,
        role=role,
        work_dir=Path.cwd(),
        session_id=task.session_id,
    )
    self._emit(OrchestratorEvent(
        task_id=task.task_id,
        event_type="agent_spawn",
        role=role,
        agent_type=type(runner).__name__,
    ))
    try:
        proc = runner.start(prompt, run_context)
        self._current_process = proc
        self._current_task_id = task.task_id
        stdout, _ = proc.communicate()
        result = RunResult(
            status="completed" if proc.returncode == 0 else "failed",
            output=stdout,
            exit_code=proc.returncode,
        )
    finally:
        self._current_process = None
        self._current_task_id = None
    output = adapter.parse_output(result)
    self._artifact_store.write(task.task_id, role, output)
    self._emit(OrchestratorEvent(
        task_id=task.task_id,
        event_type="agent_complete",
        role=role,
        notes=output.notes,
    ))
    return output
```

Also add `from system.orchestrator.schemas.run_result import RunResult` to the imports if not already present (check — it's not currently imported in orchestrator.py).

- [ ] **Step 4: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add _run_agent() shared helper with process tracking and artifact storage"
```

---

### Task 7: Structural handlers — branch_prep, doer_in_progress, retry_pending, check_failed, test_failed, qa_failed

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

These handlers do NOT call `_run_agent`. They either perform git ops or make state machine decisions. `qa_failed` is included here because its logic is a decision (reading artifact + copying `failure_source` + routing), not an agent invocation.

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/state_machine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
# --- _handle_ready_for_branch_prep ---

def test_handle_branch_prep_creates_and_pushes_branch(tmp_path):
    mock_bm = MagicMock()
    mock_bm.make_slug.return_value = "add-feature"
    mock_bm.create_branch.return_value = "feat/BRQ-1-add-feature"
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_branch_prep(task, env)
    mock_bm.create_branch.assert_called_once_with("BRQ-1", "feature", "add-feature")
    mock_bm.push.assert_called_once_with("feat/BRQ-1-add-feature")
    assert result.branch == "feat/BRQ-1-add-feature"
    assert result.state == TaskState.READY_FOR_TEST_CASE_DESIGN


def test_handle_branch_prep_blocks_on_exception(tmp_path):
    mock_bm = MagicMock()
    mock_bm.make_slug.return_value = "add-feature"
    mock_bm.create_branch.side_effect = Exception("git error")
    loop = _make_loop(tmp_path, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_branch_prep(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_doer_in_progress ---

def test_handle_doer_in_progress_transitions_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_doer_in_progress(task, env)
    assert result.state == TaskState.RETRY_PENDING


# --- _handle_retry_pending ---

def test_handle_retry_pending_retries_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_retry_pending(task, env)
    assert result.state == TaskState.DOER_IN_PROGRESS
    assert result.retry_count == 1


def test_handle_retry_pending_blocks_when_limit_reached(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_retry_pending(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_check_failed ---

def test_handle_check_failed_reworks_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_check_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 1


def test_handle_check_failed_blocks_at_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_check_failed(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_test_failed ---

def test_handle_test_failed_reworks_when_under_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=2)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_test_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 3


def test_handle_test_failed_blocks_at_limit(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_test_failed(task, env)
    assert result.state == TaskState.BLOCKED


# --- _handle_qa_failed ---

def test_handle_qa_failed_reworks_broken_implementation(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_implementation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.READY_FOR_DOER


def test_handle_qa_failed_reworks_broken_automation(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_automation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.READY_FOR_QA_AUTOMATION


def test_handle_qa_failed_blocks_on_ambiguous_criteria(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="ambiguous_criteria", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=0)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_qa_failed_blocks_at_rework_limit(tmp_path):
    loop = _make_loop(tmp_path)
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "qa_automation",
        ParsedOutput(status="fail", failure_source="broken_implementation", artifact_paths=[]))
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED, rework_count=3)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_qa_failed(task, env)
    assert result.state == TaskState.BLOCKED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_handle_branch_prep_creates_and_pushes_branch -v
```
Expected: FAIL — method doesn't exist.

- [ ] **Step 3: Implement the 6 structural handlers in orchestrator.py**

Add to `OrchestratorLoop` (after `_run_agent`):

```python
def _handle_ready_for_branch_prep(self, task: Task, env: TaskEnvelope) -> Task:
    if self._branch_manager is None:
        return self._sm.force_block(task, notes="branch_manager not configured")
    try:
        slug = BranchManager.make_slug(env.title)
        branch = self._branch_manager.create_branch(task.task_id, env.task_type, slug)
        self._branch_manager.push(branch)
    except Exception as exc:
        return self._sm.force_block(task, notes=f"branch creation failed: {exc}")
    task = task.model_copy(update={"branch": branch})
    task = self._sm.transition(task, TaskState.READY_FOR_TEST_CASE_DESIGN)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="READY_FOR_BRANCH_PREP", to_state="READY_FOR_TEST_CASE_DESIGN",
    ))
    return task


def _handle_doer_in_progress(self, task: Task, env: TaskEnvelope) -> Task:
    """Orchestrator restart mid-run — treat as crash, route to retry."""
    task = self._sm.transition(task, TaskState.RETRY_PENDING)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
        notes="crash recovery: orchestrator restarted mid-run",
    ))
    return task


def _handle_retry_pending(self, task: Task, env: TaskEnvelope) -> Task:
    if self._sm.can_transition(task, TaskState.DOER_IN_PROGRESS):
        task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="RETRY_PENDING", to_state="DOER_IN_PROGRESS",
        ))
    else:
        task = self._sm.transition(task, TaskState.BLOCKED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="RETRY_PENDING", to_state="BLOCKED",
            notes="retry limit reached",
        ))
    return task


def _handle_check_failed(self, task: Task, env: TaskEnvelope) -> Task:
    if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
        task = self._sm.transition(task, TaskState.READY_FOR_DOER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="CHECK_FAILED", to_state="READY_FOR_DOER",
        ))
    else:
        task = self._sm.transition(task, TaskState.BLOCKED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="CHECK_FAILED", to_state="BLOCKED",
            notes="rework limit reached",
        ))
    return task


def _handle_test_failed(self, task: Task, env: TaskEnvelope) -> Task:
    if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
        task = self._sm.transition(task, TaskState.READY_FOR_DOER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="TEST_FAILED", to_state="READY_FOR_DOER",
        ))
    else:
        task = self._sm.transition(task, TaskState.BLOCKED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="TEST_FAILED", to_state="BLOCKED",
            notes="rework limit reached",
        ))
    return task


def _handle_qa_failed(self, task: Task, env: TaskEnvelope) -> Task:
    qa_out = self._artifact_store.read(task.task_id, "qa_automation", ParsedOutput)
    if qa_out is not None:
        task = task.model_copy(update={"failure_source": qa_out.failure_source})
    if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
        task = self._sm.transition(task, TaskState.READY_FOR_DOER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="QA_FAILED", to_state="READY_FOR_DOER",
        ))
    elif self._sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION):
        task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="QA_FAILED", to_state="READY_FOR_QA_AUTOMATION",
        ))
    else:
        task = self._sm.transition(task, TaskState.BLOCKED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="QA_FAILED", to_state="BLOCKED",
            notes=f"failure_source={task.failure_source}",
        ))
    return task
```

- [ ] **Step 4: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add structural handlers (branch_prep, doer_crash, retry, check/test/qa_failed)"
```

---

### Task 8: Agent-invoking handlers — shaping, test_case_design, doer, checker, tester, qa, lessons

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

All handlers here call `_run_agent`. The `doer` handler is special: it first transitions to `DOER_IN_PROGRESS`, then runs the agent. The `checker` handler builds `prior_artifacts` with git diff + doer output.

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/agent_adapters/checker.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
def _mock_run_agent_pass(loop):
    """Patch _run_agent to return a passing ParsedOutput."""
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._run_agent = MagicMock(
        return_value=ParsedOutput(status="pass", artifact_paths=[], notes="ok")
    )


def _mock_run_agent_fail(loop):
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._run_agent = MagicMock(
        return_value=ParsedOutput(status="fail", artifact_paths=[], notes="fail")
    )


# --- shaping ---

def test_handle_shaping_pass_advances_to_branch_prep(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_shaping(task, env)
    assert result.state == TaskState.READY_FOR_BRANCH_PREP
    loop._run_agent.assert_called_once_with(task, env, "planner")


def test_handle_shaping_fail_blocks(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_shaping(task, env)
    assert result.state == TaskState.BLOCKED


# --- test_case_design ---

def test_handle_test_case_design_pass_advances_to_doer(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TEST_CASE_DESIGN)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_test_case_design(task, env)
    assert result.state == TaskState.READY_FOR_DOER
    loop._run_agent.assert_called_once_with(task, env, "tester")


# --- doer ---

def test_handle_doer_pass_advances_to_checker(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.READY_FOR_CHECKER


def test_handle_doer_fail_advances_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.RETRY_PENDING


def test_handle_doer_exception_advances_to_retry_pending(tmp_path):
    loop = _make_loop(tmp_path)
    loop._run_agent = MagicMock(side_effect=RuntimeError("crash"))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_doer(task, env)
    assert result.state == TaskState.RETRY_PENDING


# --- checker ---

def test_handle_checker_pass_advances_to_tester(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    mock_bm = MagicMock()
    mock_bm.diff.return_value = "diff text"
    mock_bm.merge_target.return_value = "dev"
    loop._branch_manager = mock_bm
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "doer",
        ParsedOutput(status="pass", artifact_paths=[], notes="done"))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER, branch="feat/BRQ-1-t")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_checker(task, env)
    assert result.state == TaskState.READY_FOR_TESTER
    # verify prior_artifacts passed to _run_agent
    call_kwargs = loop._run_agent.call_args
    prior = call_kwargs[1]["prior_artifacts"] if call_kwargs[1] else call_kwargs[0][3]
    assert "git_diff" in prior
    assert prior["git_diff"] == "diff text"


def test_handle_checker_fail_advances_to_check_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    mock_bm = MagicMock()
    mock_bm.diff.return_value = ""
    mock_bm.merge_target.return_value = "dev"
    loop._branch_manager = mock_bm
    from system.orchestrator.schemas.artifacts import ParsedOutput
    loop._artifact_store.write("BRQ-1", "doer",
        ParsedOutput(status="pass", artifact_paths=[], notes=""))
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER, branch="feat/BRQ-1-t")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_checker(task, env)
    assert result.state == TaskState.CHECK_FAILED


# --- tester ---

def test_handle_tester_pass_advances_to_qa(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_tester(task, env)
    assert result.state == TaskState.READY_FOR_QA_AUTOMATION


def test_handle_tester_fail_advances_to_test_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_tester(task, env)
    assert result.state == TaskState.TEST_FAILED


# --- qa ---

def test_handle_qa_pass_advances_to_merge_review(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_qa(task, env)
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW


def test_handle_qa_fail_advances_to_qa_failed(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_fail(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_qa(task, env)
    assert result.state == TaskState.QA_FAILED


# --- lessons ---

def test_handle_lessons_pass_advances_to_human_review(tmp_path):
    loop = _make_loop(tmp_path)
    _mock_run_agent_pass(loop)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_LESSONS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_lessons(task, env)
    assert result.state == TaskState.READY_FOR_HUMAN_REVIEW
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_handle_shaping_pass_advances_to_branch_prep -v
```
Expected: FAIL — `_handle_ready_for_shaping` doesn't exist.

- [ ] **Step 3: Implement the 7 agent-invoking handlers in orchestrator.py**

Add to `OrchestratorLoop` (after `_handle_qa_failed`):

```python
def _handle_ready_for_shaping(self, task: Task, env: TaskEnvelope) -> Task:
    output = self._run_agent(task, env, "planner")
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP",
        ))
    else:
        task = self._sm.force_block(task, notes="planner failed")
    return task


def _handle_ready_for_test_case_design(self, task: Task, env: TaskEnvelope) -> Task:
    output = self._run_agent(task, env, "tester")
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_DOER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_TEST_CASE_DESIGN", to_state="READY_FOR_DOER",
        ))
    else:
        task = self._sm.force_block(task, notes="test-case design failed")
    return task


def _handle_ready_for_doer(self, task: Task, env: TaskEnvelope) -> Task:
    task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="READY_FOR_DOER", to_state="DOER_IN_PROGRESS",
    ))
    try:
        output = self._run_agent(task, env, "doer")
    except Exception:
        task = self._sm.transition(task, TaskState.RETRY_PENDING)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
            notes="runner exception",
        ))
        return task
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER",
        ))
    else:
        task = self._sm.transition(task, TaskState.RETRY_PENDING)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="DOER_IN_PROGRESS", to_state="RETRY_PENDING",
        ))
    return task


def _handle_ready_for_checker(self, task: Task, env: TaskEnvelope) -> Task:
    base = self._branch_manager.merge_target(env.task_type) if self._branch_manager else "dev"
    diff = self._branch_manager.diff(task.branch or "", base) if self._branch_manager else ""
    doer_out = self._artifact_store.read(task.task_id, "doer", ParsedOutput)
    doer_notes = doer_out.notes if doer_out else ""
    prior = {
        "git_diff": diff,
        "doer_report": doer_notes,
        "failure_notes": doer_notes if task.rework_count > 0 else "",
    }
    output = self._run_agent(task, env, "checker", prior_artifacts=prior)
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_TESTER)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_CHECKER", to_state="READY_FOR_TESTER",
        ))
    else:
        task = self._sm.transition(task, TaskState.CHECK_FAILED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_CHECKER", to_state="CHECK_FAILED",
        ))
    return task


def _handle_ready_for_tester(self, task: Task, env: TaskEnvelope) -> Task:
    output = self._run_agent(task, env, "tester")
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_TESTER", to_state="READY_FOR_QA_AUTOMATION",
        ))
    else:
        task = self._sm.transition(task, TaskState.TEST_FAILED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_TESTER", to_state="TEST_FAILED",
        ))
    return task


def _handle_ready_for_qa(self, task: Task, env: TaskEnvelope) -> Task:
    output = self._run_agent(task, env, "qa_automation")
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW",
        ))
    else:
        task = self._sm.transition(task, TaskState.QA_FAILED)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_QA_AUTOMATION", to_state="QA_FAILED",
        ))
    return task


def _handle_ready_for_lessons(self, task: Task, env: TaskEnvelope) -> Task:
    output = self._run_agent(task, env, "lessons")
    if output.status == "pass":
        task = self._sm.transition(task, TaskState.READY_FOR_HUMAN_REVIEW)
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="state_transition",
            from_state="READY_FOR_LESSONS", to_state="READY_FOR_HUMAN_REVIEW",
        ))
    else:
        task = self._sm.force_block(task, notes="lessons agent failed")
    return task
```

- [ ] **Step 4: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add agent-invoking handlers (shaping, tcd, doer, checker, tester, qa, lessons)"
```

---

### Task 9: _handle_ready_for_merge_review — PR creation + CI polling

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

This is the **only non-advancing handler** — it polls CI once and stays in state if CI not yet complete. PR is created once (stored in `task.pr_url`). On CI green, writes `MergeReadinessArtifact`.

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/ci_adapter.py`, `system/orchestrator/schemas/artifacts.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
from system.orchestrator.ci_adapter import CiRun


def test_handle_merge_review_creates_pr_if_not_set(tmp_path):
    mock_gh = MagicMock()
    mock_gh.create_pr.return_value = "https://github.com/owner/repo/pull/7"
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = None  # CI not started yet
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=mock_gh, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url=None)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    mock_gh.create_pr.assert_called_once()
    assert result.pr_url == "https://github.com/owner/repo/pull/7"
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW  # CI not done, stays


def test_handle_merge_review_does_not_recreate_pr(tmp_path):
    mock_gh = MagicMock()
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = None
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=mock_gh, branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._handle_ready_for_merge_review(task, env)
    mock_gh.create_pr.assert_not_called()


def test_handle_merge_review_stays_when_ci_in_progress(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="in_progress", conclusion=None, branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.READY_FOR_MERGE_REVIEW


def test_handle_merge_review_advances_on_ci_green(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="completed", conclusion="success", branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.READY_FOR_LESSONS
    # MergeReadinessArtifact written
    from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
    artifact = loop._artifact_store.read("BRQ-1", "merge-readiness", MergeReadinessArtifact)
    assert artifact is not None
    assert artifact.verdict == "pass"


def test_handle_merge_review_blocks_on_ci_failure(tmp_path):
    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="completed", conclusion="failure", branch="feat/BRQ-1-t"
    )
    mock_bm = MagicMock()
    mock_bm.merge_target.return_value = "dev"
    loop = _make_loop(tmp_path, ci_adapter=mock_ci, github_adapter=MagicMock(), branch_manager=mock_bm)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_merge_review_blocks_when_ci_adapter_none(tmp_path):
    loop = _make_loop(tmp_path)  # no ci_adapter
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                branch="feat/BRQ-1-t", pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_merge_review(task, env)
    assert result.state == TaskState.BLOCKED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_handle_merge_review_creates_pr_if_not_set -v
```
Expected: FAIL — method doesn't exist.

- [ ] **Step 3: Implement _handle_ready_for_merge_review in orchestrator.py**

Add import at top of file:
```python
import datetime
```

Add method to `OrchestratorLoop`:

```python
def _handle_ready_for_merge_review(self, task: Task, env: TaskEnvelope) -> Task:
    # Create PR if not yet created
    if task.pr_url is None:
        if self._github_adapter is None:
            return self._sm.force_block(task, notes="github_adapter not configured")
        base = self._branch_manager.merge_target(env.task_type) if self._branch_manager else "dev"
        pr_url = self._github_adapter.create_pr(
            branch=task.branch or "",
            base=base,
            title=f"{env.task_id}: {env.title}",
            body=f"Automated PR for task {env.task_id}.",
        )
        task = task.model_copy(update={"pr_url": pr_url})

    # Non-blocking CI poll
    if self._ci_adapter is None:
        return self._sm.force_block(task, notes="ci_adapter not configured")
    run = self._ci_adapter.get_latest_run(task.branch or "")
    if run is None or run.status != "completed":
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="ci_poll",
            notes=f"CI not complete yet for {task.branch}",
        ))
        return task  # stay in READY_FOR_MERGE_REVIEW
    if run.conclusion != "success":
        self._emit(OrchestratorEvent(
            task_id=task.task_id, event_type="ci_result",
            notes=f"CI failed: conclusion={run.conclusion}",
        ))
        return self._sm.force_block(task, notes=f"CI failed: {run.conclusion}")

    # CI green — write merge-readiness artifact and advance
    base = self._branch_manager.merge_target(env.task_type) if self._branch_manager else "dev"
    artifact = MergeReadinessArtifact(
        task_id=task.task_id,
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        artifacts_present=[],
        branch=task.branch or "",
        merge_target=base,
        ci_conclusion=run.conclusion,
        branch_is_current=True,
        verdict="pass",
    )
    self._artifact_store.write(task.task_id, "merge-readiness", artifact)
    task = self._sm.transition(task, TaskState.READY_FOR_LESSONS)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="READY_FOR_MERGE_REVIEW", to_state="READY_FOR_LESSONS",
    ))
    return task
```

- [ ] **Step 4: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add _handle_ready_for_merge_review with PR creation and CI polling"
```

---

### Task 10: _handle_ready_for_human_review + _HANDLERS dict + _tick() dispatch update

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

This wires everything together. `_HANDLERS` is a module-level constant mapping `TaskState` → method name string. `_tick()` is updated to dispatch to handlers via `getattr`.

**Context to read first:** `system/orchestrator/orchestrator.py`, `system/orchestrator/state_machine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
# --- _handle_ready_for_human_review ---

def test_handle_human_review_auto_merges_and_advances_to_done(tmp_path):
    mock_gh = MagicMock()
    loop = _make_loop(tmp_path, github_adapter=mock_gh)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW,
                pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_human_review(task, env)
    mock_gh.merge_pr.assert_called_once_with("https://github.com/owner/repo/pull/5")
    assert result.state == TaskState.DONE


def test_handle_human_review_blocks_when_no_pr_url(tmp_path):
    loop = _make_loop(tmp_path, github_adapter=MagicMock())
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW, pr_url=None)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_human_review(task, env)
    assert result.state == TaskState.BLOCKED


def test_handle_human_review_blocks_when_github_adapter_none(tmp_path):
    loop = _make_loop(tmp_path)  # no github_adapter
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW,
                pr_url="https://github.com/owner/repo/pull/5")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._handle_ready_for_human_review(task, env)
    assert result.state == TaskState.BLOCKED


# --- _tick() dispatch ---

def test_tick_dispatches_to_correct_handler(tmp_path):
    loop = _make_loop(tmp_path)
    called_with = []

    def fake_handler(task, env):
        called_with.append((task.state, env.task_id))
        return task  # no state change

    loop._handle_ready_for_shaping = fake_handler
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._tick(task, env, {})
    assert len(called_with) == 1
    assert called_with[0][0] == TaskState.READY_FOR_SHAPING


def test_tick_returns_task_unchanged_for_done(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.DONE)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._tick(task, env, {})
    assert result.state == TaskState.DONE


def test_tick_returns_task_unchanged_for_blocked(tmp_path):
    loop = _make_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.BLOCKED)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    result = loop._tick(task, env, {})
    assert result.state == TaskState.BLOCKED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_handle_human_review_auto_merges_and_advances_to_done -v
```
Expected: FAIL.

- [ ] **Step 3: Implement _handle_ready_for_human_review in orchestrator.py**

Add to `OrchestratorLoop`:

```python
def _handle_ready_for_human_review(self, task: Task, env: TaskEnvelope) -> Task:
    if self._github_adapter is None:
        return self._sm.force_block(task, notes="github_adapter not configured")
    if task.pr_url is None:
        return self._sm.force_block(task, notes="pr_url not set — cannot merge")
    self._github_adapter.merge_pr(task.pr_url)
    task = self._sm.transition(task, TaskState.DONE)
    self._emit(OrchestratorEvent(
        task_id=task.task_id, event_type="state_transition",
        from_state="READY_FOR_HUMAN_REVIEW", to_state="DONE",
    ))
    return task
```

- [ ] **Step 4: Add _HANDLERS dict and update _tick()**

Add at module level in `system/orchestrator/orchestrator.py` — insert BEFORE the `OrchestratorLoop` class definition:

```python
_HANDLERS: dict[TaskState, str] = {
    TaskState.READY_FOR_SHAPING:           "_handle_ready_for_shaping",
    TaskState.READY_FOR_BRANCH_PREP:       "_handle_ready_for_branch_prep",
    TaskState.READY_FOR_TEST_CASE_DESIGN:  "_handle_ready_for_test_case_design",
    TaskState.READY_FOR_DOER:              "_handle_ready_for_doer",
    TaskState.DOER_IN_PROGRESS:            "_handle_doer_in_progress",
    TaskState.READY_FOR_CHECKER:           "_handle_ready_for_checker",
    TaskState.CHECK_FAILED:                "_handle_check_failed",
    TaskState.READY_FOR_TESTER:            "_handle_ready_for_tester",
    TaskState.TEST_FAILED:                 "_handle_test_failed",
    TaskState.READY_FOR_QA_AUTOMATION:     "_handle_ready_for_qa",
    TaskState.QA_FAILED:                   "_handle_qa_failed",
    TaskState.READY_FOR_MERGE_REVIEW:      "_handle_ready_for_merge_review",
    TaskState.READY_FOR_LESSONS:           "_handle_ready_for_lessons",
    TaskState.READY_FOR_HUMAN_REVIEW:      "_handle_ready_for_human_review",
    TaskState.RETRY_PENDING:               "_handle_retry_pending",
}
```

Replace `_tick()` in `OrchestratorLoop`:

```python
def _tick(
    self,
    task: Task,
    env: TaskEnvelope,
    all_tasks: dict[str, tuple[Task, TaskEnvelope]],
) -> Task:
    """Single tick for one task. Returns updated task."""
    if task.state in (TaskState.DONE, TaskState.BLOCKED):
        return task

    if task.state == TaskState.NEW:
        if self.check_dependency_gate(task, all_tasks):
            task = self._sm.transition(task, TaskState.READY_FOR_SHAPING)
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="state_transition",
                from_state="NEW", to_state="READY_FOR_SHAPING",
            ))
        else:
            self._emit(OrchestratorEvent(
                task_id=task.task_id, event_type="dependency_wait",
                notes="Waiting for dependencies",
            ))
        return task

    handler_name = _HANDLERS.get(task.state)
    if handler_name is None:
        return task
    return getattr(self, handler_name)(task, env)
```

- [ ] **Step 5: Run all orchestrator tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/unit/orchestrator/ -v
```
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add _HANDLERS dispatch dict, _tick() full pipeline, auto-merge handler"
```

---

### Task 11: Integration tests — happy path + rework loop

**Files:**
- Modify: `tests/unit/orchestrator/test_orchestrator_loop.py`

End-to-end tests driving a task through the full loop with mocked runners. These verify the dispatch wiring and confirm the full 17-state sequence works.

**Context to read first:** `tests/unit/orchestrator/test_orchestrator_loop.py`, `system/orchestrator/orchestrator.py`

- [ ] **Step 1: Write integration tests**

These tests are inherently "green-first" since they test composition of already-implemented handlers. Add at the end of `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
# ─── Integration tests ────────────────────────────────────────────────────────

def _make_integration_loop(tmp_path):
    """Full loop with all mocked adapters for integration testing."""
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude", "checker": "claude", "tester": "claude",
                        "qa_automation": "claude", "lessons": "claude", "planner": "claude"},
    )
    sm = ConcreteStateMachine(max_rework_loops=3, max_retries=3)
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()

    mock_bm = MagicMock()
    mock_bm.make_slug.return_value = "add-feature"
    mock_bm.create_branch.return_value = "feat/BRQ-1-add-feature"
    mock_bm.merge_target.return_value = "dev"
    mock_bm.diff.return_value = "diff text"

    mock_ci = MagicMock()
    mock_ci.get_latest_run.return_value = CiRun(
        run_id=1, status="completed", conclusion="success", branch="feat/BRQ-1-add-feature"
    )

    mock_gh = MagicMock()
    mock_gh.create_pr.return_value = "https://github.com/owner/repo/pull/99"
    mock_gh.merge_pr.return_value = None

    loop = OrchestratorLoop(
        config=cfg, state_machine=sm, artifact_store=store, event_log=log, event_queue=eq,
        branch_manager=mock_bm, ci_adapter=mock_ci, github_adapter=mock_gh,
    )

    # Mock router: all agents return pass
    from system.orchestrator.schemas.artifacts import ParsedOutput
    mock_runner = MagicMock()
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('{"status": "pass", "notes": "done"}', None)
    mock_proc.returncode = 0
    mock_runner.start.return_value = mock_proc

    mock_adapter = MagicMock()
    mock_adapter.build_prompt.return_value = "prompt"
    mock_adapter.parse_output.return_value = ParsedOutput(
        status="pass", artifact_paths=[], notes="done"
    )

    loop._router = MagicMock()
    loop._router.resolve.return_value = (mock_runner, mock_adapter)

    return loop, sm


def test_integration_happy_path_new_to_done(tmp_path):
    """Task drives NEW → DONE through all 17 states with all-passing mock agents."""
    loop, sm = _make_integration_loop(tmp_path)
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    all_tasks = {"BRQ-1": (task, env)}

    # Drive task forward until DONE or BLOCKED (max 50 ticks to avoid infinite loops)
    for _ in range(50):
        task, env = all_tasks["BRQ-1"]
        if task.state in (TaskState.DONE, TaskState.BLOCKED):
            break
        task = loop._tick(task, env, all_tasks)
        all_tasks["BRQ-1"] = (task, env)

    assert task.state == TaskState.DONE


def test_integration_rework_loop_check_failed_blocks_after_3(tmp_path):
    """Task blocked after 3 check failures (rework limit)."""
    loop, sm = _make_integration_loop(tmp_path)

    # Patch _run_agent: checker always fails, others pass
    from system.orchestrator.schemas.artifacts import ParsedOutput

    def selective_run_agent(task, env, role, prior_artifacts=None):
        if role == "checker":
            return ParsedOutput(status="fail", artifact_paths=[], notes="check failed")
        return ParsedOutput(status="pass", artifact_paths=[], notes="ok")

    loop._run_agent = selective_run_agent

    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="Add feature", task_type="feature", component="backend")
    all_tasks = {"BRQ-1": (task, env)}

    for _ in range(100):
        task, env = all_tasks["BRQ-1"]
        if task.state in (TaskState.DONE, TaskState.BLOCKED):
            break
        task = loop._tick(task, env, all_tasks)
        all_tasks["BRQ-1"] = (task, env)

    assert task.state == TaskState.BLOCKED
    # rework_count should be 3 (incremented on each CHECK_FAILED → READY_FOR_DOER)
    assert task.rework_count == 3
```

- [ ] **Step 2: Run the integration tests**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_integration_happy_path_new_to_done \
    tests/unit/orchestrator/test_orchestrator_loop.py::test_integration_rework_loop_check_failed_blocks_after_3 -v
```
Expected: Both PASS.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/unit/ -v
```
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "test(orchestrator): add integration tests for happy path and rework loop blocking"
```

---

## Running all tests

After all tasks are complete, verify the full suite:

```bash
pytest tests/unit/orchestrator/ -v --tb=short
```

Expected: All tests PASS, zero failures.

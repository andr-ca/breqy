# Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 delivery workflow orchestrator that manages the full task lifecycle from intake to merge using multiple AI providers with a Textual TUI for live visibility.

**Architecture:** State machine (18 states — spec heading says "17" but enumerates 18 including RETRY_PENDING; use 18) drives task progression through 6 agent roles (Planner, Doer, Checker, Tester, QA, Lessons). Each role is handled by a configurable AI runner (Claude, Codex, Gemini, Copilot, Qwen). The orchestrator loads tasks from GitHub Issues or local YAML, manages git branches, gates on CI, and writes all events to an append-only JSONL log consumed by the TUI.

**Tech Stack:** Python 3.12+, Pydantic v2, Textual, python-ulid, PyYAML, subprocess (git/gh/claude CLI)

**Spec:** `docs/superpowers/specs/2026-03-14-orchestrator-design.md`

---

## File Structure

```
system/orchestrator/
  __init__.py
  main.py                     # CLI entry: parse args, wire deps, start loop + TUI
  config.py                   # OrchestratorConfig, GitHubConfig, OrchestratorSettings (Pydantic)
  state_machine.py            # TaskState enum (18 states), StateMachine ABC + ConcreteStateMachine
  router.py                   # (task_type, component, role) → runner type + adapter
  task_loader.py              # TaskLoader ABC + CompositeTaskLoader
  github_task_loader.py       # GitHubTaskLoader: gh CLI + issue body parsing
  local_task_loader.py        # LocalYamlTaskLoader: glob tasks/*.yaml
  artifact_store.py           # Read/write ai-artifacts/<task_id>/*, generic typed read()
  branch_manager.py           # Git: create/rebase branch, stale check, merge target
  github_adapter.py           # gh CLI: issue labels/state, PR create/view
  ci_adapter.py               # gh run list/view — poll CI, gate on green
  session_manager.py          # Claude rate limit detection, ccusage polling, resume logic
  event_log.py                # Append-only JSONL event writer
  runners/
    __init__.py               # exports: AgentRunner, RunResult, RunContext
    base.py                   # AgentRunner ABC
    claude_runner.py
    codex_runner.py
    gemini_runner.py
    copilot_runner.py
    qwen_runner.py
  agent_adapters/
    __init__.py               # exports: AgentAdapter, TaskContext, ParsedOutput
    base.py                   # AgentAdapter ABC
    planner.py
    doer.py
    checker.py
    tester.py
    qa_automation.py
    lessons.py
  prompts/                    # markdown prompt templates (no __init__.py)
    planner.md
    doer.md
    checker.md
    tester.md
    qa_automation.md
    lessons.md
  schemas/
    __init__.py               # exports all schema types
    task_envelope.py          # TaskEnvelope
    artifacts.py              # ParsedOutput, ReviewArtifact, TestArtifact, QaArtifact,
                              # LessonsArtifact, MergeReadinessArtifact
    run_result.py             # RunResult, RunContext
    events.py                 # OrchestratorEvent
  tui/
    __init__.py
    app.py                    # Textual App: root layout, queue watcher, mounts panels
    panels/
      __init__.py
      task_panel.py
      pipeline_panel.py
      agent_panel.py
      log_panel.py
  tasks/                      # local YAML task fallback (add to .gitignore, keep .gitkeep)

tests/unit/orchestrator/
  __init__.py
  test_schemas.py             # TaskEnvelope, RunResult, artifacts, OrchestratorEvent
  test_config.py
  test_state_machine.py
  test_artifact_store.py
  test_event_log.py
  test_branch_manager.py
  test_session_manager.py
  test_github_adapter.py
  test_ci_adapter.py
  test_task_loader.py
  test_router.py
  runners/
    __init__.py
    test_claude_runner.py
    test_codex_runner.py
    test_gemini_runner.py
    test_copilot_runner.py
    test_qwen_runner.py
  agent_adapters/
    __init__.py
    test_planner.py
    test_doer.py
    test_checker.py
    test_tester.py
    test_qa_automation.py
    test_lessons.py

tests/integration/orchestrator/
  __init__.py
  test_orchestrator_loop.py   # local YAML task → DONE with mocked runners

ai-artifacts/                 # task artifact output (gitignored)
.breqy/orchestrator/          # runtime state + event log (gitignored)
```

---

## Chunk 1: Foundation — Schemas, Config, State Machine

### Task 1: Project setup

**Files:**
- Modify: `pyproject.toml`
- Create: all `__init__.py` stubs
- Create: `.env.sample` additions
- Create: `system/orchestrator/tasks/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add to `[project] dependencies`:
```toml
"textual>=0.71.0",
"python-ulid>=2.0.0",
"pyyaml>=6.0.1",
```

- [ ] **Step 2: Install new deps**

```bash
uv sync
```
Expected: resolves without errors.

- [ ] **Step 3: Create directory structure and __init__.py stubs**

```bash
mkdir -p system/orchestrator/schemas system/orchestrator/runners \
  system/orchestrator/agent_adapters system/orchestrator/tui/panels \
  system/orchestrator/prompts system/orchestrator/tasks \
  tests/unit/orchestrator/runners tests/unit/orchestrator/agent_adapters \
  tests/integration/orchestrator
touch system/orchestrator/__init__.py \
  system/orchestrator/schemas/__init__.py \
  system/orchestrator/runners/__init__.py \
  system/orchestrator/agent_adapters/__init__.py \
  system/orchestrator/tui/__init__.py \
  "system/orchestrator/tui/panels/__init__.py" \
  system/orchestrator/tasks/.gitkeep \
  tests/unit/orchestrator/__init__.py \
  tests/unit/orchestrator/runners/__init__.py \
  tests/unit/orchestrator/agent_adapters/__init__.py \
  tests/integration/orchestrator/__init__.py
```

- [ ] **Step 4: Add gitignore entries**

Add to `.gitignore`:
```
ai-artifacts/
.breqy/orchestrator/
system/orchestrator/tasks/*.yaml
```

- [ ] **Step 5: Add orchestrator vars to .env.sample**

```bash
# GitHub
GITHUB_TOKEN=                   # required: gh CLI auth token

# AI provider API keys (only set keys for providers used in routing_rules)
ANTHROPIC_API_KEY=              # Claude runners
OPENAI_API_KEY=                 # Codex runners
GOOGLE_API_KEY=                 # Gemini runners
GITHUB_COPILOT_TOKEN=           # Copilot runners
DASHSCOPE_API_KEY=              # Qwen runners (Alibaba DashScope)
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml system/orchestrator/ tests/unit/orchestrator/ \
  tests/integration/orchestrator/ .env.sample .gitignore
git commit -m "chore: scaffold orchestrator package structure and deps"
```

---

### Task 2: TaskEnvelope schema

**Files:**
- Create: `system/orchestrator/schemas/task_envelope.py`
- Create: `tests/unit/orchestrator/test_schemas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/orchestrator/test_schemas.py
import pytest
from pydantic import ValidationError
from system.orchestrator.schemas.task_envelope import TaskEnvelope


def test_task_envelope_minimal():
    env = TaskEnvelope(
        task_id="BRQ-1",
        title="Test task",
        task_type="feature",
        component="backend",
    )
    assert env.task_id == "BRQ-1"
    assert env.dependencies == []
    assert env.acceptance_criteria == []


def test_task_envelope_full():
    env = TaskEnvelope(
        task_id="BRQ-144",
        title="Session resume flow",
        description="Allow resuming sessions after rate limit",
        task_type="feature",
        component="backend",
        dependencies=["BRQ-100", "BRQ-101"],
        acceptance_criteria=["Sessions persist across restarts"],
        test_hints=["Test with mock rate limit response"],
        priority="high",
        labels=["orchestrator:managed"],
        github_issue_number=144,
    )
    assert env.github_issue_number == 144
    assert len(env.dependencies) == 2


def test_task_envelope_requires_task_id():
    with pytest.raises(ValidationError):
        TaskEnvelope(title="No ID", task_type="feature", component="backend")


def test_task_envelope_valid_task_types():
    for t in ("feature", "bug", "refactor", "hotfix"):
        env = TaskEnvelope(task_id="BRQ-1", title="t", task_type=t, component="backend")
        assert env.task_type == t


def test_task_envelope_invalid_task_type():
    with pytest.raises(ValidationError):
        TaskEnvelope(task_id="BRQ-1", title="t", task_type="unknown", component="backend")
```

- [ ] **Step 2: Run test — verify fails**

```bash
pytest tests/unit/orchestrator/test_schemas.py -v
```
Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement TaskEnvelope**

```python
# system/orchestrator/schemas/task_envelope.py
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
```

- [ ] **Step 4: Run test — verify passes**

```bash
pytest tests/unit/orchestrator/test_schemas.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/schemas/task_envelope.py tests/unit/orchestrator/test_schemas.py
git commit -m "feat: add TaskEnvelope schema"
```

---

### Task 3: RunResult and RunContext schemas

**Files:**
- Create: `system/orchestrator/schemas/run_result.py`
- Modify: `tests/unit/orchestrator/test_schemas.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/orchestrator/test_schemas.py
from pathlib import Path
from pydantic import ValidationError
from system.orchestrator.schemas.run_result import RunResult, RunContext


def test_run_result_completed():
    r = RunResult(status="completed", output="done", exit_code=0)
    assert r.session_id is None
    assert r.artifacts_written == []


def test_run_result_rate_limited():
    r = RunResult(status="rate_limited", output="", exit_code=1, session_id="sid-abc")
    assert r.status == "rate_limited"
    assert r.session_id == "sid-abc"


def test_run_result_invalid_status():
    with pytest.raises(ValidationError):
        RunResult(status="unknown", output="", exit_code=0)


def test_run_context_defaults():
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    assert ctx.session_id is None
    assert ctx.extra_env == {}


def test_run_context_extra_env_independent():
    ctx1 = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    ctx2 = RunContext(task_id="BRQ-2", role="doer", work_dir=Path("/tmp"))
    ctx1.extra_env["KEY"] = "val"
    assert "KEY" not in ctx2.extra_env
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_schemas.py::test_run_result_completed \
  tests/unit/orchestrator/test_schemas.py::test_run_result_rate_limited -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/schemas/run_result.py
from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


RunStatus = Literal["completed", "rate_limited", "failed"]


class RunResult(BaseModel):
    status: RunStatus
    output: str
    exit_code: int
    session_id: str | None = None
    artifacts_written: list[str] = []


class RunContext(BaseModel):
    task_id: str
    role: str
    work_dir: Path
    session_id: str | None = None
    extra_env: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_schemas.py -k "run_result or run_context" -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/schemas/run_result.py tests/unit/orchestrator/test_schemas.py
git commit -m "feat: add RunResult and RunContext schemas"
```

---

### Task 4: Artifact schemas

**Files:**
- Create: `system/orchestrator/schemas/artifacts.py`
- Modify: `tests/unit/orchestrator/test_schemas.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/orchestrator/test_schemas.py
from system.orchestrator.schemas.artifacts import (
    ParsedOutput,
    ReviewArtifact,
    TestArtifact,
    QaArtifact,
    LessonsArtifact,
    MergeReadinessArtifact,
)


def test_parsed_output_pass():
    p = ParsedOutput(status="pass", artifact_paths=["ai-artifacts/BRQ-1/doer-report.json"])
    assert p.failure_source is None
    assert p.notes == ""


def test_parsed_output_fail_with_source():
    p = ParsedOutput(
        status="fail",
        artifact_paths=[],
        failure_source="broken_implementation",
        notes="Tests failing",
    )
    assert p.failure_source == "broken_implementation"


def test_parsed_output_invalid_status():
    with pytest.raises(ValidationError):
        ParsedOutput(status="maybe", artifact_paths=[])


def test_review_artifact():
    r = ReviewArtifact(status="pass", findings=[], summary="LGTM")
    assert r.status == "pass"


def test_test_artifact():
    t = TestArtifact(status="fail", tests_run=10, tests_failed=2)
    assert t.tests_failed == 2


def test_qa_artifact_failure_source():
    q = QaArtifact(status="fail", failure_source="broken_automation")
    assert q.failure_source == "broken_automation"


def test_lessons_artifact():
    la = LessonsArtifact(task_id="BRQ-1", lessons=["Use mocks carefully"])
    assert la.instruction_update_proposed is False


def test_merge_readiness_artifact_pass():
    m = MergeReadinessArtifact(
        task_id="BRQ-1",
        checked_at="2026-03-14T14:00:00Z",
        artifacts_present=["task-envelope", "doer-report"],
        branch="feat/BRQ-1-test",
        merge_target="dev",
        ci_conclusion="success",
        branch_is_current=True,
        verdict="pass",
    )
    assert m.verdict == "pass"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_schemas.py::test_parsed_output_pass \
  tests/unit/orchestrator/test_schemas.py::test_review_artifact -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/schemas/artifacts.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class ParsedOutput(BaseModel):
    status: Literal["pass", "fail"]
    artifact_paths: list[str]
    failure_source: str | None = None
    session_id: str | None = None
    notes: str = ""


class ReviewArtifact(BaseModel):
    status: Literal["pass", "fail"]
    findings: list[str]
    summary: str = ""


class TestArtifact(BaseModel):
    status: Literal["pass", "fail"]
    tests_run: int = 0
    tests_failed: int = 0
    output: str = ""


class QaArtifact(BaseModel):
    status: Literal["pass", "fail"]
    failure_source: (
        Literal["broken_implementation", "broken_automation", "ambiguous_criteria"] | None
    ) = None
    output: str = ""


class LessonsArtifact(BaseModel):
    task_id: str
    lessons: list[str]
    instruction_update_proposed: bool = False


class MergeReadinessArtifact(BaseModel):
    task_id: str
    checked_at: str
    artifacts_present: list[str]
    branch: str
    merge_target: str
    ci_conclusion: str
    branch_is_current: bool
    verdict: Literal["pass", "fail"]
    notes: str = ""
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_schemas.py -k \
  "parsed_output or review_artifact or test_artifact or qa_artifact or lessons_artifact or merge_readiness" -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/schemas/artifacts.py tests/unit/orchestrator/test_schemas.py
git commit -m "feat: add artifact schemas (ParsedOutput, Review, Test, QA, Lessons, MergeReadiness)"
```

---

### Task 5: OrchestratorEvent schema

**Files:**
- Create: `system/orchestrator/schemas/events.py`
- Create: `system/orchestrator/schemas/__init__.py` (populate)
- Modify: `tests/unit/orchestrator/test_schemas.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/orchestrator/test_schemas.py
from system.orchestrator.schemas.events import OrchestratorEvent


def test_orchestrator_event_minimal():
    e = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition")
    assert e.event_id        # ULID generated
    assert e.timestamp       # ISO8601 generated
    assert e.from_state is None
    assert e.artifact_paths == []


def test_orchestrator_event_full():
    e = OrchestratorEvent(
        task_id="BRQ-144",
        event_type="state_transition",
        from_state="READY_FOR_DOER",
        to_state="DOER_IN_PROGRESS",
        role="doer",
        agent_type="claude",
        artifact_paths=["ai-artifacts/BRQ-144/doer-report.json"],
        notes="Starting doer run",
    )
    assert e.to_state == "DOER_IN_PROGRESS"
    assert len(e.artifact_paths) == 1


def test_orchestrator_event_unique_ids():
    e1 = OrchestratorEvent(task_id="BRQ-1", event_type="agent_spawn")
    e2 = OrchestratorEvent(task_id="BRQ-1", event_type="agent_spawn")
    assert e1.event_id != e2.event_id
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_schemas.py::test_orchestrator_event_minimal -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement events.py**

```python
# system/orchestrator/schemas/events.py
from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from ulid import ULID


def _ulid() -> str:
    return str(ULID())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestratorEvent(BaseModel):
    event_id: str = Field(default_factory=_ulid)
    timestamp: str = Field(default_factory=_now_iso)
    task_id: str
    event_type: str   # state_transition | agent_spawn | agent_complete | artifact_written |
                      # ci_poll | ci_result | rate_limit | rework_loop | blocked | error |
                      # dependency_wait | stale_warning | retry_pending
    from_state: str | None = None
    to_state: str | None = None
    role: str | None = None
    agent_type: str | None = None
    artifact_paths: list[str] = []
    notes: str = ""
```

- [ ] **Step 4: Populate schemas/__init__.py**

```python
# system/orchestrator/schemas/__init__.py
from .task_envelope import TaskEnvelope, TaskType
from .run_result import RunResult, RunContext, RunStatus
from .artifacts import (
    ParsedOutput,
    ReviewArtifact,
    TestArtifact,
    QaArtifact,
    LessonsArtifact,
    MergeReadinessArtifact,
)
from .events import OrchestratorEvent

__all__ = [
    "TaskEnvelope", "TaskType",
    "RunResult", "RunContext", "RunStatus",
    "ParsedOutput", "ReviewArtifact", "TestArtifact",
    "QaArtifact", "LessonsArtifact", "MergeReadinessArtifact",
    "OrchestratorEvent",
]
```

- [ ] **Step 5: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_schemas.py -v
```
Expected: all schema tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/schemas/ tests/unit/orchestrator/test_schemas.py
git commit -m "feat: add OrchestratorEvent schema and wire schemas/__init__.py"
```

---

### Task 6: Config model + orchestrator.yaml template

**Files:**
- Create: `system/orchestrator/config.py`
- Create: `system/orchestrator/orchestrator.yaml`
- Create: `tests/unit/orchestrator/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_config.py
import textwrap
from pathlib import Path
import pytest
from system.orchestrator.config import OrchestratorConfig, load_config


MINIMAL_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo

    orchestrator:
      poll_interval_seconds: 30
      max_rework_loops: 3
      max_retries: 3

    agent_defaults:
      doer: claude
      checker: codex
      tester: gemini
      lessons: claude
""")

ROUTING_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo

    orchestrator:
      max_rework_loops: 3
      max_retries: 3

    agent_defaults:
      doer: claude

    routing_rules:
      feature:
        backend:
          doer: qwen
          checker: codex
""")


def test_load_config_minimal(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.github.repo == "owner/repo"
    assert cfg.orchestrator.max_rework_loops == 3
    assert cfg.agent_defaults["doer"] == "claude"


def test_config_github_defaults(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.github.ci_timeout_minutes == 30
    assert cfg.github.ci_poll_interval_seconds == 60
    assert cfg.github.managed_label == "orchestrator:managed"


def test_config_orchestrator_defaults(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(MINIMAL_YAML)
    cfg = load_config(cfg_file)
    assert cfg.orchestrator.branch_stale_days == 3
    assert cfg.orchestrator.artifact_base == "ai-artifacts"


def test_config_routing_rules(tmp_path):
    cfg_file = tmp_path / "orchestrator.yaml"
    cfg_file.write_text(ROUTING_YAML)
    cfg = load_config(cfg_file)
    assert cfg.routing_rules["feature"]["backend"]["doer"] == "qwen"
    assert cfg.routing_rules["feature"]["backend"]["checker"] == "codex"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/orchestrator.yaml"))
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_config.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement config.py**

```python
# system/orchestrator/config.py
from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel


class GitHubConfig(BaseModel):
    repo: str
    managed_label: str = "orchestrator:managed"
    ci_timeout_minutes: int = 30
    ci_poll_interval_seconds: int = 60


class OrchestratorSettings(BaseModel):
    poll_interval_seconds: int = 30
    max_rework_loops: int = 3
    max_retries: int = 3
    retry_backoff_seconds: int = 60
    artifact_base: str = "ai-artifacts"
    event_log: str = ".breqy/orchestrator/events.jsonl"
    runtime_state: str = ".breqy/orchestrator/runtime-state.yaml"
    task_fallback_dir: str = "system/orchestrator/tasks"
    branch_stale_days: int = 3


class OrchestratorConfig(BaseModel):
    github: GitHubConfig
    orchestrator: OrchestratorSettings = OrchestratorSettings()
    routing_rules: dict[str, dict[str, dict[str, str]]] = {}
    agent_defaults: dict[str, str] = {}


def load_config(path: Path) -> OrchestratorConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text())
    return OrchestratorConfig.model_validate(data)
```

- [ ] **Step 4: Create orchestrator.yaml template**

```yaml
# system/orchestrator/orchestrator.yaml
github:
  repo: owner/repo          # EDIT: your GitHub repo (owner/name)
  managed_label: orchestrator:managed
  ci_timeout_minutes: 30
  ci_poll_interval_seconds: 60

orchestrator:
  poll_interval_seconds: 30
  max_rework_loops: 3
  max_retries: 3
  retry_backoff_seconds: 60
  artifact_base: ai-artifacts
  event_log: .breqy/orchestrator/events.jsonl
  runtime_state: .breqy/orchestrator/runtime-state.yaml
  task_fallback_dir: system/orchestrator/tasks
  branch_stale_days: 3

agent_defaults:
  planner:       claude
  doer:          claude
  checker:       codex
  tester:        gemini
  qa_automation: claude
  lessons:       claude

routing_rules:
  feature:
    backend:
      planner:       claude
      doer:          claude
      checker:       codex
      tester:        gemini
      qa_automation: claude
      lessons:       claude
    tui:
      planner:       claude
      doer:          claude
      checker:       qwen
      tester:        gemini
      qa_automation: gemini
      lessons:       claude
  bug:
    low_risk:
      doer:          copilot
      checker:       codex
      tester:        gemini
      lessons:       claude
  refactor:
    service:
      doer:          qwen
      checker:       codex
      tester:        gemini
      lessons:       claude
```

- [ ] **Step 5: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_config.py -v
```
Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/config.py system/orchestrator/orchestrator.yaml \
  tests/unit/orchestrator/test_config.py
git commit -m "feat: add OrchestratorConfig model and orchestrator.yaml template (includes Qwen routing)"
```

---

### Task 7: TaskState enum + StateMachine ABC

**Files:**
- Create: `system/orchestrator/state_machine.py`
- Create: `tests/unit/orchestrator/test_state_machine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_state_machine.py
import pytest
from system.orchestrator.state_machine import TaskState, StateMachine, Task


def test_task_state_count():
    # Spec heading says "17 states" but enumerates 18 including RETRY_PENDING.
    # We implement all 18 as listed in the spec's transition table.
    states = list(TaskState)
    assert len(states) == 18


def test_task_state_values():
    assert TaskState.NEW == "NEW"
    assert TaskState.DONE == "DONE"
    assert TaskState.BLOCKED == "BLOCKED"
    assert TaskState.RETRY_PENDING == "RETRY_PENDING"
    assert TaskState.QA_FAILED == "QA_FAILED"
    assert TaskState.READY_FOR_MERGE_REVIEW == "READY_FOR_MERGE_REVIEW"


def test_task_model_defaults():
    t = Task(task_id="BRQ-1", state=TaskState.NEW)
    assert t.rework_count == 0
    assert t.retry_count == 0
    assert t.failure_source is None
    assert t.branch is None


def test_state_machine_is_abstract():
    with pytest.raises(TypeError):
        StateMachine()
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_state_machine.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement TaskState, Task, StateMachine ABC**

```python
# system/orchestrator/state_machine.py
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel


class TaskState(str, Enum):
    NEW = "NEW"
    READY_FOR_SHAPING = "READY_FOR_SHAPING"
    READY_FOR_BRANCH_PREP = "READY_FOR_BRANCH_PREP"
    READY_FOR_TEST_CASE_DESIGN = "READY_FOR_TEST_CASE_DESIGN"
    READY_FOR_DOER = "READY_FOR_DOER"
    DOER_IN_PROGRESS = "DOER_IN_PROGRESS"
    READY_FOR_CHECKER = "READY_FOR_CHECKER"
    CHECK_FAILED = "CHECK_FAILED"
    READY_FOR_TESTER = "READY_FOR_TESTER"
    TEST_FAILED = "TEST_FAILED"
    READY_FOR_QA_AUTOMATION = "READY_FOR_QA_AUTOMATION"
    QA_FAILED = "QA_FAILED"
    READY_FOR_MERGE_REVIEW = "READY_FOR_MERGE_REVIEW"
    READY_FOR_LESSONS = "READY_FOR_LESSONS"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    RETRY_PENDING = "RETRY_PENDING"


class Task(BaseModel):
    task_id: str
    state: TaskState
    rework_count: int = 0
    retry_count: int = 0
    failure_source: str | None = None
    session_id: str | None = None
    branch: str | None = None
    github_issue_number: int | None = None
    pr_url: str | None = None


class StateMachine(ABC):
    @abstractmethod
    def can_transition(self, task: Task, to: TaskState) -> bool:
        """Return True if the guard-gated transition is allowed given task state.
        Note: READY_FOR_MERGE_REVIEW → READY_FOR_LESSONS additionally requires
        CI green + merge-readiness artifact — these external gates are checked by
        the orchestrator loop BEFORE calling transition(), not inside can_transition().
        """
        ...

    @abstractmethod
    def transition(self, task: Task, to: TaskState) -> Task:
        """Apply the transition and return a new Task. Increments rework_count or
        retry_count as appropriate for rework/retry transitions."""
        ...

    @abstractmethod
    def force_block(self, task: Task, notes: str = "") -> Task:
        """Emergency/manual block — moves any non-terminal task to BLOCKED
        unconditionally. Use for operator intervention, not guard logic."""
        ...
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_state_machine.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/state_machine.py tests/unit/orchestrator/test_state_machine.py
git commit -m "feat: add TaskState enum (18 states), Task model, StateMachine ABC"
```

---

### Task 8: ConcreteStateMachine — all transitions, guards, counter increments

**Files:**
- Modify: `system/orchestrator/state_machine.py`
- Modify: `tests/unit/orchestrator/test_state_machine.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/orchestrator/test_state_machine.py
from system.orchestrator.state_machine import ConcreteStateMachine, InvalidTransitionError


@pytest.fixture
def sm():
    return ConcreteStateMachine(max_rework_loops=3, max_retries=3)


@pytest.fixture
def new_task():
    return Task(task_id="BRQ-1", state=TaskState.NEW)


# --- Happy path transitions ---

def test_new_to_shaping_allowed(sm, new_task):
    # Dep guard is orchestrator loop's responsibility, not SM's.
    # SM only enforces structural state validity.
    assert sm.can_transition(new_task, TaskState.READY_FOR_SHAPING)


def test_transition_new_to_shaping(sm, new_task):
    result = sm.transition(new_task, TaskState.READY_FOR_SHAPING)
    assert result.state == TaskState.READY_FOR_SHAPING


def test_full_happy_path_transitions(sm):
    """Verify each consecutive normal-path transition is allowed."""
    happy_path = [
        TaskState.NEW,
        TaskState.READY_FOR_SHAPING,
        TaskState.READY_FOR_BRANCH_PREP,
        TaskState.READY_FOR_TEST_CASE_DESIGN,
        TaskState.READY_FOR_DOER,
        TaskState.DOER_IN_PROGRESS,
        TaskState.READY_FOR_CHECKER,
        TaskState.READY_FOR_TESTER,
        TaskState.READY_FOR_QA_AUTOMATION,
        TaskState.READY_FOR_MERGE_REVIEW,
        TaskState.READY_FOR_LESSONS,
        TaskState.READY_FOR_HUMAN_REVIEW,
        TaskState.DONE,
    ]
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    for to_state in happy_path[1:]:
        assert sm.can_transition(task, to_state), f"Expected {task.state} → {to_state} to be allowed"
        task = sm.transition(task, to_state)
    assert task.state == TaskState.DONE


# --- Invalid transition ---

def test_invalid_transition_raises(sm, new_task):
    with pytest.raises(InvalidTransitionError):
        sm.transition(new_task, TaskState.DONE)


# --- Rework: CHECK_FAILED ---

def test_check_failed_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=1)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.state == TaskState.READY_FOR_DOER
    assert result.rework_count == 2   # incremented


def test_check_failed_to_blocked_not_allowed_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=1)
    assert not sm.can_transition(task, TaskState.BLOCKED)


def test_check_failed_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=3)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Rework: TEST_FAILED ---

def test_test_failed_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.rework_count == 1   # incremented


def test_test_failed_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=3)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Rework: QA_FAILED ---

def test_qa_failed_broken_impl_routes_to_doer(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_implementation", rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert not sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    result = sm.transition(task, TaskState.READY_FOR_DOER)
    assert result.rework_count == 1


def test_qa_failed_broken_automation_routes_to_qa(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_automation", rework_count=0)
    assert sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    result = sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert result.rework_count == 1


def test_qa_failed_ambiguous_always_blocks(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="ambiguous_criteria", rework_count=0)
    assert not sm.can_transition(task, TaskState.READY_FOR_DOER)
    assert not sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION)
    assert sm.can_transition(task, TaskState.BLOCKED)


def test_qa_failed_blocked_not_allowed_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                failure_source="broken_implementation", rework_count=1)
    assert not sm.can_transition(task, TaskState.BLOCKED)


# --- DOER_IN_PROGRESS error paths ---

def test_doer_in_progress_to_retry_pending(sm):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    assert sm.can_transition(task, TaskState.RETRY_PENDING)
    result = sm.transition(task, TaskState.RETRY_PENDING)
    assert result.state == TaskState.RETRY_PENDING
    assert result.retry_count == 0   # not incremented here; incremented on exit from RETRY_PENDING


def test_doer_in_progress_to_blocked_only_at_retry_limit(sm):
    # BLOCKED from DOER_IN_PROGRESS requires retry_count >= max_retries
    task_within = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, retry_count=1)
    assert not sm.can_transition(task_within, TaskState.BLOCKED)
    task_at_limit = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, retry_count=3)
    assert sm.can_transition(task_at_limit, TaskState.BLOCKED)


# --- Retry ---

def test_retry_pending_to_doer_within_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=1)
    assert sm.can_transition(task, TaskState.DOER_IN_PROGRESS)
    result = sm.transition(task, TaskState.DOER_IN_PROGRESS)
    assert result.retry_count == 2   # incremented


def test_retry_pending_to_blocked_at_limit(sm):
    task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=3)
    assert not sm.can_transition(task, TaskState.DOER_IN_PROGRESS)
    assert sm.can_transition(task, TaskState.BLOCKED)


# --- Force block ---

def test_force_block_from_any_state(sm):
    for state in TaskState:
        if state in (TaskState.DONE, TaskState.BLOCKED):
            continue
        task = Task(task_id="BRQ-1", state=state)
        result = sm.force_block(task, notes="operator override")
        assert result.state == TaskState.BLOCKED


def test_force_block_no_effect_on_done(sm):
    task = Task(task_id="BRQ-1", state=TaskState.DONE)
    result = sm.force_block(task)
    assert result.state == TaskState.DONE   # DONE is terminal, no-op
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_state_machine.py -k "not test_task_state and not test_state_machine_is_abstract and not test_task_model" -v
```
Expected: `ImportError` (ConcreteStateMachine not defined).

- [ ] **Step 3: Implement ConcreteStateMachine**

```python
# append to system/orchestrator/state_machine.py

class InvalidTransitionError(Exception):
    pass


# Structural transitions (no guard counters needed).
# BLOCKED is NOT in these tables — it is guard-gated per state.
_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.NEW: {TaskState.READY_FOR_SHAPING},
    TaskState.READY_FOR_SHAPING: {TaskState.READY_FOR_BRANCH_PREP},
    TaskState.READY_FOR_BRANCH_PREP: {TaskState.READY_FOR_TEST_CASE_DESIGN},
    TaskState.READY_FOR_TEST_CASE_DESIGN: {TaskState.READY_FOR_DOER},
    TaskState.READY_FOR_DOER: {TaskState.DOER_IN_PROGRESS},
    TaskState.DOER_IN_PROGRESS: {TaskState.READY_FOR_CHECKER, TaskState.RETRY_PENDING},
    TaskState.READY_FOR_CHECKER: {TaskState.READY_FOR_TESTER, TaskState.CHECK_FAILED},
    TaskState.READY_FOR_TESTER: {TaskState.READY_FOR_QA_AUTOMATION, TaskState.TEST_FAILED},
    TaskState.READY_FOR_QA_AUTOMATION: {TaskState.READY_FOR_MERGE_REVIEW, TaskState.QA_FAILED},
    # READY_FOR_MERGE_REVIEW → READY_FOR_LESSONS is structurally allowed here.
    # The CI green + merge-readiness artifact gates are checked by the orchestrator
    # loop BEFORE calling transition() — they are not enforced inside can_transition().
    TaskState.READY_FOR_MERGE_REVIEW: {TaskState.READY_FOR_LESSONS},
    TaskState.READY_FOR_LESSONS: {TaskState.READY_FOR_HUMAN_REVIEW},
    TaskState.READY_FOR_HUMAN_REVIEW: {TaskState.DONE},
    TaskState.BLOCKED: set(),
    TaskState.DONE: set(),
}

# States where BLOCKED is guard-gated (only when limit exceeded)
_BLOCKED_ON_LIMIT = {
    TaskState.DOER_IN_PROGRESS,   # retry_count >= max_retries
    TaskState.CHECK_FAILED,        # rework_count >= max_rework_loops
    TaskState.TEST_FAILED,         # rework_count >= max_rework_loops
    TaskState.QA_FAILED,           # rework_count >= max_rework_loops OR ambiguous_criteria
    TaskState.RETRY_PENDING,       # retry_count >= max_retries
}

# States where BLOCKED is always allowed (manual operator block, no guard required)
_BLOCKED_UNCONDITIONAL = set(TaskState) - _BLOCKED_ON_LIMIT - {TaskState.BLOCKED, TaskState.DONE}


class ConcreteStateMachine(StateMachine):
    def __init__(self, max_rework_loops: int = 3, max_retries: int = 3) -> None:
        self.max_rework_loops = max_rework_loops
        self.max_retries = max_retries

    def can_transition(self, task: Task, to: TaskState) -> bool:
        # --- BLOCKED rules (guard-gated per state) ---
        if to == TaskState.BLOCKED:
            if task.state in _BLOCKED_UNCONDITIONAL:
                return True
            if task.state == TaskState.DOER_IN_PROGRESS:
                return task.retry_count >= self.max_retries
            if task.state == TaskState.CHECK_FAILED:
                return task.rework_count >= self.max_rework_loops
            if task.state == TaskState.TEST_FAILED:
                return task.rework_count >= self.max_rework_loops
            if task.state == TaskState.QA_FAILED:
                return (
                    task.failure_source == "ambiguous_criteria"
                    or task.rework_count >= self.max_rework_loops
                )
            if task.state == TaskState.RETRY_PENDING:
                return task.retry_count >= self.max_retries
            return False

        # --- Rework loop rules ---
        if task.state in (TaskState.CHECK_FAILED, TaskState.TEST_FAILED):
            if to == TaskState.READY_FOR_DOER:
                return task.rework_count < self.max_rework_loops
            return False

        if task.state == TaskState.QA_FAILED:
            if to == TaskState.READY_FOR_DOER:
                return (
                    task.failure_source == "broken_implementation"
                    and task.rework_count < self.max_rework_loops
                )
            if to == TaskState.READY_FOR_QA_AUTOMATION:
                return (
                    task.failure_source == "broken_automation"
                    and task.rework_count < self.max_rework_loops
                )
            return False

        if task.state == TaskState.RETRY_PENDING:
            if to == TaskState.DOER_IN_PROGRESS:
                return task.retry_count < self.max_retries
            return False

        # --- Structural transitions ---
        return to in _ALLOWED.get(task.state, set())

    def transition(self, task: Task, to: TaskState) -> Task:
        if not self.can_transition(task, to):
            raise InvalidTransitionError(
                f"Cannot transition {task.task_id} from {task.state} to {to}"
            )
        updates: dict = {"state": to}
        # Increment rework_count on rework transitions
        if task.state in (TaskState.CHECK_FAILED, TaskState.TEST_FAILED) and to == TaskState.READY_FOR_DOER:
            updates["rework_count"] = task.rework_count + 1
        if task.state == TaskState.QA_FAILED and to in (TaskState.READY_FOR_DOER, TaskState.READY_FOR_QA_AUTOMATION):
            updates["rework_count"] = task.rework_count + 1
        # Increment retry_count on retry transition
        if task.state == TaskState.RETRY_PENDING and to == TaskState.DOER_IN_PROGRESS:
            updates["retry_count"] = task.retry_count + 1
        return task.model_copy(update=updates)

    def force_block(self, task: Task, notes: str = "") -> Task:
        """Unconditional operator block. DONE is terminal — no-op."""
        if task.state in (TaskState.DONE, TaskState.BLOCKED):
            return task
        return task.model_copy(update={"state": TaskState.BLOCKED})
```

- [ ] **Step 4: Run — verify all state machine tests pass**

```bash
pytest tests/unit/orchestrator/test_state_machine.py -v
```
Expected: all tests PASSED (~24 tests).

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/state_machine.py tests/unit/orchestrator/test_state_machine.py
git commit -m "feat: implement ConcreteStateMachine with guards, counter increments, and force_block"
```

---

## Chunk 2: Infrastructure — ArtifactStore, EventLog, BranchManager, SessionManager, Adapters, Loaders

### Task 9: ArtifactStore

**Files:**
- Create: `system/orchestrator/artifact_store.py`
- Create: `tests/unit/orchestrator/test_artifact_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_artifact_store.py
import pytest
from pathlib import Path
from pydantic import BaseModel
from system.orchestrator.artifact_store import ArtifactStore


class _SampleModel(BaseModel):
    value: str
    count: int = 0


def test_write_and_read_model(tmp_path):
    store = ArtifactStore(base=tmp_path)
    obj = _SampleModel(value="hello", count=42)
    path = store.write("BRQ-1", "doer-report", obj)
    assert path.exists()
    result = store.read("BRQ-1", "doer-report", _SampleModel)
    assert result is not None
    assert result.value == "hello"
    assert result.count == 42


def test_write_and_read_text(tmp_path):
    store = ArtifactStore(base=tmp_path)
    store.write("BRQ-1", "lessons-learned", "# Lessons\n- Use mocks carefully")
    text = store.read_text("BRQ-1", "lessons-learned")
    assert text is not None
    assert "Use mocks carefully" in text


def test_exists(tmp_path):
    store = ArtifactStore(base=tmp_path)
    assert not store.exists("BRQ-1", "doer-report")
    store.write("BRQ-1", "doer-report", _SampleModel(value="x"))
    assert store.exists("BRQ-1", "doer-report")


def test_read_missing_returns_none(tmp_path):
    store = ArtifactStore(base=tmp_path)
    assert store.read("BRQ-1", "doer-report", _SampleModel) is None
    assert store.read_text("BRQ-1", "lessons-learned") is None


def test_write_creates_task_directory(tmp_path):
    store = ArtifactStore(base=tmp_path)
    store.write("BRQ-99", "test-artifact", _SampleModel(value="y"))
    assert (tmp_path / "BRQ-99").is_dir()


def test_model_stored_as_json(tmp_path):
    store = ArtifactStore(base=tmp_path)
    obj = _SampleModel(value="test")
    path = store.write("BRQ-1", "doer-report", obj)
    # JSON extension for Pydantic models
    assert path.suffix == ".json"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_artifact_store.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/artifact_store.py
from __future__ import annotations
import json
from pathlib import Path
from typing import TypeVar, overload
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ArtifactStore:
    """Read/write task artifacts under base/<task_id>/.

    Pydantic models → .json (JSON serialised via model_dump_json).
    Plain str → .md (markdown or plain text).
    """

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
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_artifact_store.py -v
```
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/artifact_store.py tests/unit/orchestrator/test_artifact_store.py
git commit -m "feat: add ArtifactStore with typed read/write"
```

---

### Task 10: EventLog

**Files:**
- Create: `system/orchestrator/event_log.py`
- Create: `tests/unit/orchestrator/test_event_log.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_event_log.py
import json
import pytest
from pathlib import Path
from system.orchestrator.event_log import EventLog
from system.orchestrator.schemas.events import OrchestratorEvent


def test_append_creates_file(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="state_transition")
    log.append(event)
    assert (tmp_path / "events.jsonl").exists()


def test_append_writes_valid_json_line(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    event = OrchestratorEvent(task_id="BRQ-1", event_type="agent_spawn", role="doer")
    log.append(event)
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["task_id"] == "BRQ-1"
    assert data["event_type"] == "agent_spawn"
    assert data["role"] == "doer"


def test_append_multiple_events(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    for i in range(5):
        log.append(OrchestratorEvent(task_id=f"BRQ-{i}", event_type="test"))
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 5


def test_tail_returns_last_n(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    for i in range(10):
        log.append(OrchestratorEvent(task_id=f"BRQ-{i}", event_type="test"))
    events = log.tail(3)
    assert len(events) == 3
    assert events[-1].task_id == "BRQ-9"


def test_tail_on_empty_file(tmp_path):
    log = EventLog(path=tmp_path / "events.jsonl")
    assert log.tail(5) == []


def test_creates_parent_directory(tmp_path):
    log = EventLog(path=tmp_path / "nested" / "dir" / "events.jsonl")
    log.append(OrchestratorEvent(task_id="BRQ-1", event_type="test"))
    assert log._path.exists()
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_event_log.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/event_log.py
from __future__ import annotations
import json
from pathlib import Path
from system.orchestrator.schemas.events import OrchestratorEvent


class EventLog:
    """Append-only JSONL writer. Thread-safe for single-writer use."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: OrchestratorEvent) -> None:
        with self._path.open("a") as f:
            f.write(event.model_dump_json() + "\n")

    def tail(self, n: int) -> list[OrchestratorEvent]:
        if not self._path.exists():
            return []
        lines = self._path.read_text().strip().splitlines()
        return [OrchestratorEvent.model_validate_json(line) for line in lines[-n:]]
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_event_log.py -v
```
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/event_log.py tests/unit/orchestrator/test_event_log.py
git commit -m "feat: add append-only EventLog (JSONL)"
```

---

### Task 11: BranchManager

**Files:**
- Create: `system/orchestrator/branch_manager.py`
- Create: `tests/unit/orchestrator/test_branch_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_branch_manager.py
import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.branch_manager import BranchManager, BranchError


@pytest.fixture
def bm(tmp_path):
    return BranchManager(repo_root=tmp_path)


def _run_ok(cmd, **_):
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


def test_make_slug():
    assert BranchManager.make_slug("Session resume flow and retry") == "session-resume-flow-and-retry"
    assert BranchManager.make_slug("Fix: reconnect!") == "fix-reconnect"
    assert len(BranchManager.make_slug("x" * 100)) == 40


def test_branch_name_feature(bm):
    slug = BranchManager.make_slug("session resume flow and retry")
    name = bm._make_branch_name("BRQ-144", "feature", slug)
    assert name.startswith("feat/BRQ-144-")
    assert " " not in name


def test_branch_name_bug(bm):
    assert bm._make_branch_name("BRQ-201", "bug", "fix-reconnect").startswith("fix/")


def test_branch_name_refactor(bm):
    assert bm._make_branch_name("BRQ-233", "refactor", "cleanup").startswith("refactor/")


def test_branch_name_hotfix(bm):
    assert bm._make_branch_name("BRQ-299", "hotfix", "critical-auth").startswith("hotfix/")


def test_create_branch_calls_git_checkout(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        name = bm.create_branch("BRQ-1", "feature", "session-resume")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "checkout" in calls
        assert "-b" in calls
    assert name == "feat/BRQ-1-session-resume"


def test_current_branch_returns_name(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="feat/BRQ-1-test\n", stderr="")
        assert bm.current_branch() == "feat/BRQ-1-test"


def test_is_stale_false_for_recent(bm):
    import time
    recent_ts = str(int(time.time()) - 60)   # 1 minute ago
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=recent_ts, stderr="")
        assert not bm.is_stale("feat/BRQ-1-test", max_age_days=3)


def test_is_stale_true_for_old(bm):
    import time
    old_ts = str(int(time.time()) - 7 * 86400)   # 7 days ago
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=old_ts, stderr="")
        assert bm.is_stale("feat/BRQ-1-test", max_age_days=3)


def test_rebase_calls_git_rebase(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        bm.rebase("feat/BRQ-1-test", "dev")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "rebase" in calls


def test_merge_target_feature(bm):
    assert bm.merge_target("feature") == "dev"


def test_merge_target_hotfix(bm):
    assert bm.merge_target("hotfix") == "main"


def test_merge_target_bug_and_refactor(bm):
    assert bm.merge_target("bug") == "dev"
    assert bm.merge_target("refactor") == "dev"


def test_branch_exists_true(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert bm.branch_exists("feat/BRQ-1-test")


def test_branch_exists_false(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert not bm.branch_exists("feat/BRQ-1-test")


def test_push_calls_git(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        bm.push("feat/BRQ-1-test")
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("push" in c for c in calls)
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_branch_manager.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/branch_manager.py
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
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_branch_manager.py -v
```
Expected: 19 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/branch_manager.py tests/unit/orchestrator/test_branch_manager.py
git commit -m "feat: add BranchManager (git branch lifecycle)"
```

---

### Task 12: SessionManager

**Files:**
- Create: `system/orchestrator/session_manager.py`
- Create: `tests/unit/orchestrator/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_session_manager.py
import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.session_manager import SessionManager, is_rate_limit_output


def test_is_rate_limit_output_positive():
    assert is_rate_limit_output("Error: Claude AI rate limit exceeded")
    assert is_rate_limit_output("claude: rate_limit_error: too many requests")
    assert is_rate_limit_output("Overloaded")


def test_is_rate_limit_output_negative():
    assert not is_rate_limit_output("Implementation complete")
    assert not is_rate_limit_output("")
    assert not is_rate_limit_output("Error: file not found")


def test_session_manager_stores_session_id():
    sm = SessionManager()
    sm.save_session("BRQ-1", "doer", "sess-abc-123")
    assert sm.get_session("BRQ-1", "doer") == "sess-abc-123"


def test_session_manager_returns_none_for_unknown():
    sm = SessionManager()
    assert sm.get_session("BRQ-999", "doer") is None


def test_session_manager_overwrite():
    sm = SessionManager()
    sm.save_session("BRQ-1", "doer", "old-id")
    sm.save_session("BRQ-1", "doer", "new-id")
    assert sm.get_session("BRQ-1", "doer") == "new-id"


def test_ccusage_available_when_zero_blocks():
    sm = SessionManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"blocks": 0}', stderr=""
        )
        assert sm.is_window_available()


def test_ccusage_blocked_when_blocks_nonzero():
    sm = SessionManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"blocks": 2}', stderr=""
        )
        assert not sm.is_window_available()
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_session_manager.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/session_manager.py
from __future__ import annotations
import json
import subprocess

_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "overloaded",
    "too many requests",
)


def is_rate_limit_output(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _RATE_LIMIT_KEYWORDS)


class SessionManager:
    """Claude-specific session continuity: stores session IDs, polls ccusage."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], str] = {}

    def save_session(self, task_id: str, role: str, session_id: str) -> None:
        self._sessions[(task_id, role)] = session_id

    def get_session(self, task_id: str, role: str) -> str | None:
        return self._sessions.get((task_id, role))

    def is_window_available(self) -> bool:
        """True if ccusage reports zero active blocks (rate limit window clear)."""
        try:
            result = subprocess.run(
                ["ccusage", "blocks", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("blocks", 1) == 0
        except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
            pass
        return True   # assume available if ccusage not installed
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_session_manager.py -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/session_manager.py tests/unit/orchestrator/test_session_manager.py
git commit -m "feat: add SessionManager (Claude session continuity and rate limit detection)"
```

---

### Task 13: GitHubAdapter

**Files:**
- Create: `system/orchestrator/github_adapter.py`
- Create: `tests/unit/orchestrator/test_github_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_github_adapter.py
import json
import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.github_adapter import GitHubAdapter, PrStatus


def _run_ok(stdout="", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


@pytest.fixture
def gh():
    return GitHubAdapter(repo="owner/repo")


def test_set_task_state_adds_new_label(gh):
    with patch("subprocess.run", return_value=_run_ok()) as mock_run:
        gh.set_task_state(42, "DOER_IN_PROGRESS")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "state:DOER_IN_PROGRESS" in calls
        assert "--add-label" in calls


def test_set_task_state_removes_old_label(gh):
    with patch("subprocess.run", return_value=_run_ok()) as mock_run:
        gh.set_task_state(42, "DOER_IN_PROGRESS", old_state="READY_FOR_DOER")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "state:READY_FOR_DOER" in calls   # old label removed
        assert "--remove-label" in calls
        assert "state:DOER_IN_PROGRESS" in calls  # new label added


def test_get_task_state_returns_state(gh):
    payload = json.dumps({"labels": [{"name": "orchestrator:managed"}, {"name": "state:READY_FOR_DOER"}]})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        state = gh.get_task_state(42)
    assert state == "READY_FOR_DOER"


def test_get_task_state_returns_none_when_no_state_label(gh):
    payload = json.dumps({"labels": [{"name": "orchestrator:managed"}]})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        assert gh.get_task_state(42) is None


def test_create_pr_returns_url(gh):
    pr_url = "https://github.com/owner/repo/pull/5"
    with patch("subprocess.run", return_value=_run_ok(stdout=pr_url)):
        url = gh.create_pr("feat/BRQ-1-test", "My PR", "Body text")
        assert url == pr_url.strip()


def test_pr_is_merged_true(gh):
    with patch("subprocess.run", return_value=_run_ok(stdout='{"state":"MERGED"}')):
        assert gh.pr_is_merged("https://github.com/owner/repo/pull/5")


def test_pr_is_merged_false(gh):
    with patch("subprocess.run", return_value=_run_ok(stdout='{"state":"OPEN"}')):
        assert not gh.pr_is_merged("https://github.com/owner/repo/pull/5")


def test_get_pr_status(gh):
    payload = json.dumps({"state": "OPEN", "mergeable": "MERGEABLE", "url": "http://x"})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        status = gh.get_pr_status("http://x")
        assert status.state == "OPEN"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_github_adapter.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/github_adapter.py
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

    def set_task_state(self, issue_number: int, new_state: str, old_state: str | None = None) -> None:
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
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_github_adapter.py -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/github_adapter.py tests/unit/orchestrator/test_github_adapter.py
git commit -m "feat: add GitHubAdapter (issue labels, PR management)"
```

---

### Task 14: CIAdapter

**Files:**
- Create: `system/orchestrator/ci_adapter.py`
- Create: `tests/unit/orchestrator/test_ci_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_ci_adapter.py
import json
import pytest
from unittest.mock import patch, MagicMock, call
from system.orchestrator.ci_adapter import CIAdapter, CiRun


def _run_ok(stdout=""):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


@pytest.fixture
def ci():
    return CIAdapter(repo="owner/repo", poll_interval_seconds=0)


def test_get_latest_run_success(ci):
    payload = json.dumps([{"databaseId": 1, "status": "completed",
                           "conclusion": "success", "headBranch": "feat/BRQ-1"}])
    with patch("subprocess.run", return_value=_run_ok(payload)):
        run = ci.get_latest_run("feat/BRQ-1")
        assert run.conclusion == "success"
        assert run.status == "completed"


def test_get_latest_run_no_runs_returns_none(ci):
    with patch("subprocess.run", return_value=_run_ok("[]")):
        assert ci.get_latest_run("feat/BRQ-1") is None


def test_wait_for_green_immediate(ci):
    payload = json.dumps([{"databaseId": 1, "status": "completed",
                           "conclusion": "success", "headBranch": "feat/BRQ-1"}])
    with patch("subprocess.run", return_value=_run_ok(payload)):
        assert ci.wait_for_green("feat/BRQ-1", timeout_minutes=1)


def test_wait_for_green_failure_returns_false(ci):
    payload = json.dumps([{"databaseId": 1, "status": "completed",
                           "conclusion": "failure", "headBranch": "feat/BRQ-1"}])
    with patch("subprocess.run", return_value=_run_ok(payload)):
        assert not ci.wait_for_green("feat/BRQ-1", timeout_minutes=1)


def test_wait_for_green_timeout_returns_false(ci):
    # in_progress run — never completes
    payload = json.dumps([{"databaseId": 1, "status": "in_progress",
                           "conclusion": None, "headBranch": "feat/BRQ-1"}])
    with patch("subprocess.run", return_value=_run_ok(payload)):
        # timeout_minutes=0 expires immediately
        assert not ci.wait_for_green("feat/BRQ-1", timeout_minutes=0)
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_ci_adapter.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/ci_adapter.py
from __future__ import annotations
import json
import subprocess
import time
from pydantic import BaseModel


class CiRun(BaseModel):
    run_id: int
    status: str
    conclusion: str | None
    branch: str


class CIAdapter:
    def __init__(
        self, repo: str, poll_interval_seconds: int = 60,
        event_log: "EventLog | None" = None,
        task_id: str = "",
    ) -> None:
        self._repo = repo
        self._poll_interval = poll_interval_seconds
        self._log = event_log
        self._task_id = task_id

    def _emit(self, event_type: str, notes: str = "") -> None:
        if self._log:
            from system.orchestrator.schemas.events import OrchestratorEvent
            self._log.append(OrchestratorEvent(
                task_id=self._task_id, event_type=event_type, notes=notes
            ))

    def get_latest_run(self, branch: str) -> CiRun | None:
        result = subprocess.run(
            ["gh", "run", "list", "--repo", self._repo,
             "--branch", branch, "--json", "databaseId,status,conclusion,headBranch",
             "--limit", "1"],
            capture_output=True, text=True,
        )
        runs = json.loads(result.stdout or "[]")
        if not runs:
            return None
        r = runs[0]
        return CiRun(
            run_id=r["databaseId"],
            status=r["status"],
            conclusion=r.get("conclusion"),
            branch=r["headBranch"],
        )

    def wait_for_green(self, branch: str, timeout_minutes: int = 30) -> bool:
        deadline = time.monotonic() + timeout_minutes * 60
        while time.monotonic() < deadline:
            run = self.get_latest_run(branch)
            self._emit("ci_poll", notes=f"branch={branch} status={run.status if run else 'no-run'}")
            if run and run.status == "completed":
                if run.conclusion == "success":
                    self._emit("ci_result", notes=f"branch={branch} conclusion=success")
                    return True
                else:
                    self._emit("ci_result", notes=f"branch={branch} conclusion={run.conclusion}")
                    return False
            if time.monotonic() >= deadline:
                break
            time.sleep(self._poll_interval)
        return False
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_ci_adapter.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/ci_adapter.py tests/unit/orchestrator/test_ci_adapter.py
git commit -m "feat: add CIAdapter (gh run polling, green gate)"
```

---

### Task 15: LocalYamlTaskLoader + TaskLoader ABC

**Files:**
- Create: `system/orchestrator/local_task_loader.py`
- Create: `system/orchestrator/task_loader.py` (ABC only, CompositeTaskLoader in Task 16)
- Create: `tests/unit/orchestrator/test_task_loader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_task_loader.py
import pytest
import yaml
from pathlib import Path
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader


SAMPLE_TASK = {
    "task_id": "BRQ-1",
    "title": "Test task",
    "task_type": "feature",
    "component": "backend",
}


def test_local_loader_loads_yaml_files(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "BRQ-1.yaml").write_text(yaml.dump(SAMPLE_TASK))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    tasks = loader.load_pending()
    assert len(tasks) == 1
    assert tasks[0].task_id == "BRQ-1"


def test_local_loader_empty_dir(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    assert loader.load_pending() == []


def test_local_loader_skips_invalid_yaml(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "bad.yaml").write_text("not: valid: yaml: {{{")
    (tasks_dir / "good.yaml").write_text(yaml.dump(SAMPLE_TASK))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    tasks = loader.load_pending()
    assert len(tasks) == 1   # bad file skipped


def test_local_loader_multiple_files(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    for i in range(3):
        t = {**SAMPLE_TASK, "task_id": f"BRQ-{i}"}
        (tasks_dir / f"BRQ-{i}.yaml").write_text(yaml.dump(t))
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    assert len(loader.load_pending()) == 3


def test_task_loader_is_abstract():
    with pytest.raises(TypeError):
        TaskLoader()
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_task_loader.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement task_loader.py ABC and local_task_loader.py**

```python
# system/orchestrator/task_loader.py
from __future__ import annotations
from abc import ABC, abstractmethod
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class TaskLoader(ABC):
    @abstractmethod
    def load_pending(self) -> list[TaskEnvelope]: ...
```

```python
# system/orchestrator/local_task_loader.py
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import ValidationError
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.schemas.task_envelope import TaskEnvelope


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
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_task_loader.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/task_loader.py system/orchestrator/local_task_loader.py \
  tests/unit/orchestrator/test_task_loader.py
git commit -m "feat: add TaskLoader ABC and LocalYamlTaskLoader"
```

---

### Task 16: GitHubTaskLoader + CompositeTaskLoader

**Files:**
- Create: `system/orchestrator/github_task_loader.py`
- Modify: `system/orchestrator/task_loader.py` (add CompositeTaskLoader)
- Modify: `tests/unit/orchestrator/test_task_loader.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/unit/orchestrator/test_task_loader.py
import json
from unittest.mock import patch, MagicMock
from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.task_loader import CompositeTaskLoader


ISSUE_BODY = """
Some intro text.

```yaml
task_id: BRQ-144
title: Session resume flow
task_type: feature
component: backend
```

More text.
"""

ISSUE_JSON = json.dumps([{
    "number": 144,
    "title": "Session resume flow",
    "body": ISSUE_BODY,
    "labels": [{"name": "orchestrator:managed"}],
}])


def test_github_loader_parses_issue_body():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=ISSUE_JSON, stderr="")
        loader = GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed")
        tasks = loader.load_pending()
    assert len(tasks) == 1
    assert tasks[0].task_id == "BRQ-144"
    assert tasks[0].github_issue_number == 144


def test_github_loader_skips_issues_without_yaml_block():
    no_yaml = json.dumps([{
        "number": 1,
        "title": "No YAML",
        "body": "Just plain text",
        "labels": [{"name": "orchestrator:managed"}],
    }])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=no_yaml, stderr="")
        loader = GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed")
        assert loader.load_pending() == []


def test_composite_github_primary(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    # Same task_id in both — GitHub takes priority
    (tasks_dir / "BRQ-144.yaml").write_text(yaml.dump({
        **SAMPLE_TASK, "task_id": "BRQ-144", "title": "Local version"
    }))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=ISSUE_JSON, stderr="")
        composite = CompositeTaskLoader(
            github=GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed"),
            local=LocalYamlTaskLoader(tasks_dir=tasks_dir),
        )
        tasks = composite.load_pending()
    # Only one BRQ-144 — GitHub version wins
    brq_144 = [t for t in tasks if t.task_id == "BRQ-144"]
    assert len(brq_144) == 1
    assert brq_144[0].github_issue_number == 144
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_task_loader.py::test_github_loader_parses_issue_body \
  tests/unit/orchestrator/test_task_loader.py::test_composite_github_primary -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/github_task_loader.py
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
```

Add `CompositeTaskLoader` to `task_loader.py`:

```python
# append to system/orchestrator/task_loader.py

class CompositeTaskLoader(TaskLoader):
    """GitHub Issues primary; local YAML fallback. GitHub wins on same task_id."""

    def __init__(self, github: TaskLoader, local: TaskLoader) -> None:
        self._github = github
        self._local = local

    def load_pending(self) -> list[TaskEnvelope]:
        github_tasks = self._github.load_pending()
        github_ids = {t.task_id for t in github_tasks}
        local_tasks = [t for t in self._local.load_pending() if t.task_id not in github_ids]
        return github_tasks + local_tasks
```

- [ ] **Step 4: Run — verify all task loader tests pass**

```bash
pytest tests/unit/orchestrator/test_task_loader.py -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/github_task_loader.py system/orchestrator/task_loader.py \
  tests/unit/orchestrator/test_task_loader.py
git commit -m "feat: add GitHubTaskLoader and CompositeTaskLoader"
```

---

## Chunk 3: Runners, Agent Adapters, Router

### Task 17: AgentRunner ABC + RunContext

**Files:**
- Create: `system/orchestrator/runners/base.py`
- Create: `system/orchestrator/runners/__init__.py` (populate)
- Create: `tests/unit/orchestrator/runners/test_runners_base.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/orchestrator/runners/test_runners_base.py
import pytest
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from pathlib import Path


def test_agent_runner_is_abstract():
    with pytest.raises(TypeError):
        AgentRunner()


def test_runner_interface():
    """Verify subclass must implement run()."""
    class MyRunner(AgentRunner):
        def run(self, prompt: str, context: RunContext) -> RunResult:
            return RunResult(status="completed", output="ok", exit_code=0)

    runner = MyRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hello", ctx)
    assert result.status == "completed"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/runners/test_runners_base.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/runners/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from system.orchestrator.schemas.run_result import RunContext, RunResult


class AgentRunner(ABC):
    @abstractmethod
    def run(self, prompt: str, context: RunContext) -> RunResult:
        """Spawn subprocess, stream output, handle rate limits, return result."""
        ...
```

```python
# system/orchestrator/runners/__init__.py
from .base import AgentRunner
from system.orchestrator.schemas.run_result import RunResult, RunContext

__all__ = ["AgentRunner", "RunResult", "RunContext"]
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/runners/test_runners_base.py -v
```
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/runners/ tests/unit/orchestrator/runners/
git commit -m "feat: add AgentRunner ABC"
```

---

### Task 18: ClaudeRunner

**Files:**
- Create: `system/orchestrator/runners/claude_runner.py`
- Create: `tests/unit/orchestrator/runners/test_claude_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/runners/test_claude_runner.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.schemas.run_result import RunContext


@pytest.fixture
def ctx():
    return RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))


def _proc(stdout="", returncode=0):
    m = MagicMock()
    # stdout must be a line-iterable (ClaudeRunner iterates `for line in proc.stdout`)
    m.stdout = iter(stdout.splitlines(keepends=True))
    m.stderr = ""
    m.returncode = returncode
    m.wait.return_value = returncode
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


def test_claude_runner_success(ctx):
    with patch("subprocess.Popen", return_value=_proc(stdout='Result complete\n')):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "completed"
    assert result.exit_code == 0


def test_claude_runner_rate_limit_detected(ctx):
    with patch("subprocess.Popen", return_value=_proc(
        stdout="rate_limit_error: too many requests", returncode=1
    )):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "rate_limited"


def test_claude_runner_resumes_session(ctx):
    ctx_with_session = ctx.model_copy(update={"session_id": "sess-abc"})
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _proc(stdout="done\n")
        runner = ClaudeRunner()
        runner.run("do the thing", ctx_with_session)
        cmd = mock_popen.call_args[0][0]
        assert "--resume" in cmd
        assert "sess-abc" in cmd


def test_claude_runner_builds_correct_base_cmd(ctx):
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _proc(stdout="done\n")
        runner = ClaudeRunner()
        runner.run("prompt text", ctx)
        cmd = mock_popen.call_args[0][0]
        assert "claude" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd


def test_claude_runner_exit0_with_rate_limit_string_is_rate_limited(ctx):
    """Exit code 0 + rate-limit string → rate_limited, not completed."""
    with patch("subprocess.Popen", return_value=_proc(
        stdout="rate_limit_error: too many requests\n", returncode=0
    )):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "rate_limited"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/runners/test_claude_runner.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/runners/claude_runner.py
from __future__ import annotations
import subprocess
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.session_manager import is_rate_limit_output


class ClaudeRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if context.session_id:
            cmd += ["--resume", context.session_id]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=self._env(context),
        )
        output_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            output_lines.append(line)
        proc.wait()
        output = "".join(output_lines)

        if is_rate_limit_output(output):
            return RunResult(status="rate_limited", output=output, exit_code=proc.returncode)
        if proc.returncode != 0:
            return RunResult(status="failed", output=output, exit_code=proc.returncode)
        return RunResult(status="completed", output=output, exit_code=0)

    def _env(self, context: RunContext) -> dict[str, str]:
        import os
        env = os.environ.copy()
        env.update(context.extra_env)
        return env
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/runners/test_claude_runner.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/runners/claude_runner.py \
  tests/unit/orchestrator/runners/test_claude_runner.py
git commit -m "feat: add ClaudeRunner (claude -p, stream-json, session resume)"
```

---

### Task 19: CodexRunner, GeminiRunner, CopilotRunner, QwenRunner

**Files:**
- Create: `system/orchestrator/runners/codex_runner.py`
- Create: `system/orchestrator/runners/gemini_runner.py`
- Create: `system/orchestrator/runners/copilot_runner.py`
- Create: `system/orchestrator/runners/qwen_runner.py`
- Create: `tests/unit/orchestrator/runners/test_other_runners.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/runners/test_other_runners.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.copilot_runner import CopilotRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.schemas.run_result import RunContext


@pytest.fixture
def ctx():
    return RunContext(task_id="BRQ-1", role="checker", work_dir=Path("/tmp"))


def _proc(stdout="done\n", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.wait.return_value = returncode
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


@pytest.mark.parametrize("RunnerCls,expected_cmd_token", [
    (CodexRunner, "codex"),
    (GeminiRunner, "gemini"),
    (CopilotRunner, "gh"),
    (QwenRunner, "qwen"),
])
def test_runner_invokes_correct_cli(RunnerCls, expected_cmd_token, ctx):
    with patch("subprocess.Popen", return_value=_proc()) as mock_popen:
        runner = RunnerCls()
        result = runner.run("check this code", ctx)
    cmd = mock_popen.call_args[0][0]
    assert expected_cmd_token in cmd
    assert result.status == "completed"


@pytest.mark.parametrize("RunnerCls", [CodexRunner, GeminiRunner, CopilotRunner, QwenRunner])
def test_runner_returns_failed_on_nonzero_exit(RunnerCls, ctx):
    with patch("subprocess.Popen", return_value=_proc(stdout="error output", returncode=1)):
        runner = RunnerCls()
        result = runner.run("check this code", ctx)
    assert result.status == "failed"
    assert result.exit_code == 1
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/runners/test_other_runners.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement all four runners**

```python
# system/orchestrator/runners/codex_runner.py
from __future__ import annotations
import subprocess, os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class CodexRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["codex", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        assert proc.stdout is not None
        output = proc.stdout.read()
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

```python
# system/orchestrator/runners/gemini_runner.py
from __future__ import annotations
import subprocess, os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class GeminiRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["gemini", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        assert proc.stdout is not None
        output = proc.stdout.read()
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

```python
# system/orchestrator/runners/copilot_runner.py
from __future__ import annotations
import subprocess, os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class CopilotRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["gh", "copilot", "suggest", prompt],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        assert proc.stdout is not None
        output = proc.stdout.read()
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

```python
# system/orchestrator/runners/qwen_runner.py
from __future__ import annotations
import subprocess, os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class QwenRunner(AgentRunner):
    """Qwen runner via Alibaba DashScope CLI (qwen).
    Requires DASHSCOPE_API_KEY in environment.
    Session continuity: TBD — depends on qwen CLI support."""

    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["qwen", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        assert proc.stdout is not None
        output = proc.stdout.read()
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/runners/test_other_runners.py -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Update runners/__init__.py to export all runners**

```python
# system/orchestrator/runners/__init__.py
from .base import AgentRunner
from .claude_runner import ClaudeRunner
from .codex_runner import CodexRunner
from .gemini_runner import GeminiRunner
from .copilot_runner import CopilotRunner
from .qwen_runner import QwenRunner
from system.orchestrator.schemas.run_result import RunResult, RunContext

__all__ = [
    "AgentRunner",
    "ClaudeRunner", "CodexRunner", "GeminiRunner", "CopilotRunner", "QwenRunner",
    "RunResult", "RunContext",
]
```

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/runners/ tests/unit/orchestrator/runners/test_other_runners.py
git commit -m "feat: add CodexRunner, GeminiRunner, CopilotRunner, QwenRunner; update runners __init__"
```

---

### Task 20: AgentAdapter ABC + prompt loading

**Files:**
- Create: `system/orchestrator/agent_adapters/base.py`
- Create: `system/orchestrator/agent_adapters/__init__.py` (populate)
- Create: all six `system/orchestrator/prompts/*.md` templates
- Create: `tests/unit/orchestrator/agent_adapters/test_adapter_base.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/agent_adapters/test_adapter_base.py
import pytest
from pathlib import Path
from pydantic import BaseModel
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


def test_agent_adapter_is_abstract():
    with pytest.raises(TypeError):
        AgentAdapter()


def test_task_context():
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    ctx = TaskContext(task=env, prior_artifacts={}, rework_count=0)
    assert ctx.task.task_id == "BRQ-1"
    assert ctx.prior_artifacts == {}


def test_adapter_loads_prompt_template(tmp_path):
    prompt_file = tmp_path / "doer.md"
    prompt_file.write_text("# Doer Prompt\nDo the work.")

    class ConcreteAdapter(AgentAdapter):
        role = "doer"
        prompts_dir = tmp_path

        def build_prompt(self, task, context):
            return self._load_template() + f"\n## Task\n{task.title}"

        def parse_output(self, result):
            from system.orchestrator.schemas.artifacts import ParsedOutput
            return ParsedOutput(status="pass", artifact_paths=[])

    adapter = ConcreteAdapter()
    env = TaskEnvelope(task_id="BRQ-1", title="My task", task_type="feature", component="backend")
    ctx = TaskContext(task=env, prior_artifacts={}, rework_count=0)
    prompt = adapter.build_prompt(env, ctx)
    assert "Doer Prompt" in prompt
    assert "My task" in prompt
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/agent_adapters/test_adapter_base.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement base.py and TaskContext**

```python
# system/orchestrator/agent_adapters/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class TaskContext(BaseModel):
    task: TaskEnvelope
    prior_artifacts: dict[str, str]   # name → file path
    rework_count: int = 0
    failure_notes: str = ""


class AgentAdapter(ABC):
    role: str = ""
    prompts_dir: Path = _PROMPTS_DIR

    def _load_template(self) -> str:
        path = self.prompts_dir / f"{self.role}.md"
        if path.exists():
            return path.read_text()
        return f"# {self.role.capitalize()} role\n"

    @abstractmethod
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str: ...

    @abstractmethod
    def parse_output(self, result: RunResult) -> ParsedOutput: ...
```

- [ ] **Step 4: Create six prompt templates**

```markdown
<!-- system/orchestrator/prompts/planner.md -->
# Planner Role

You are the Planner. Given a task envelope, produce a detailed shaped task specification.

## Output
Write a `doer-instructions.yaml` with:
- implementation_approach: str
- files_to_create: list[str]
- files_to_modify: list[str]
- test_strategy: str
- acceptance_criteria: list[str]
```

```markdown
<!-- system/orchestrator/prompts/doer.md -->
# Doer Role

You are the Doer. Implement the task following TDD (Red-Green-Refactor).

## Rules
- Write failing tests FIRST
- Implement minimum code to pass
- Commit frequently with conventional commit messages

## Output
Write `doer-report.json` with: status, files_changed, tests_added, notes
```

```markdown
<!-- system/orchestrator/prompts/checker.md -->
# Checker Role

You are the Checker. Review the implementation produced by the Doer.

## Input
- Git diff of changes
- doer-report.json

## Output
Write `checker-report.yaml` with: status (pass/fail), findings (list), summary
```

```markdown
<!-- system/orchestrator/prompts/tester.md -->
# Tester Role

You are the Tester. Run the full test suite and validate coverage.

## Output
Write `deterministic-test-report.json` with: status, tests_run, tests_failed, coverage_pct, output
```

```markdown
<!-- system/orchestrator/prompts/qa_automation.md -->
# QA Automation Role

You are the QA Automation engineer. Write or update automated acceptance tests.

## Output
Write `qa-automation-report.json` with: status, failure_source (broken_implementation|broken_automation|ambiguous_criteria|null), output
```

```markdown
<!-- system/orchestrator/prompts/lessons.md -->
# Lessons Role

You are the Lessons engineer. Review the full task audit trail and extract lessons.

## Input
All task artifacts in ai-artifacts/<task_id>/

## Output
- `lessons.yaml`: task_id, lessons (list), instruction_update_proposed (bool)
- `lessons-learned.md`: human-readable narrative
- `instruction-update-proposal.md` (only if instruction_update_proposed=true)
```

- [ ] **Step 5: Run — verify passes**

```bash
pytest tests/unit/orchestrator/agent_adapters/test_adapter_base.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/agent_adapters/base.py system/orchestrator/agent_adapters/__init__.py \
  system/orchestrator/prompts/ tests/unit/orchestrator/agent_adapters/test_adapter_base.py
git commit -m "feat: add AgentAdapter ABC, TaskContext, and six prompt templates"
```

---

### Task 21: Six role adapters

**Files:**
- Create: `system/orchestrator/agent_adapters/planner.py`
- Create: `system/orchestrator/agent_adapters/doer.py`
- Create: `system/orchestrator/agent_adapters/checker.py`
- Create: `system/orchestrator/agent_adapters/tester.py`
- Create: `system/orchestrator/agent_adapters/qa_automation.py`
- Create: `system/orchestrator/agent_adapters/lessons.py`
- Create: `tests/unit/orchestrator/agent_adapters/test_role_adapters.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/agent_adapters/test_role_adapters.py
import json
import pytest
from pathlib import Path
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.agent_adapters.base import TaskContext
from system.orchestrator.agent_adapters.planner import PlannerAdapter
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.agent_adapters.checker import CheckerAdapter
from system.orchestrator.agent_adapters.tester import TesterAdapter
from system.orchestrator.agent_adapters.qa_automation import QaAutomationAdapter
from system.orchestrator.agent_adapters.lessons import LessonsAdapter


@pytest.fixture
def task():
    return TaskEnvelope(task_id="BRQ-1", title="Session resume", task_type="feature", component="backend")


@pytest.fixture
def ctx(task):
    return TaskContext(task=task, prior_artifacts={}, rework_count=0)


@pytest.fixture
def pass_result():
    return RunResult(status="completed", output='{"status": "pass"}', exit_code=0)


@pytest.fixture
def fail_result():
    return RunResult(
        status="completed",
        output=json.dumps({"status": "fail", "failure_source": "broken_implementation"}),
        exit_code=0,
    )


def test_planner_build_prompt_contains_task_id(task, ctx):
    adapter = PlannerAdapter()
    prompt = adapter.build_prompt(task, ctx)
    assert "BRQ-1" in prompt


def test_doer_build_prompt_contains_acceptance_criteria(ctx):
    task = TaskEnvelope(
        task_id="BRQ-1", title="t", task_type="feature", component="backend",
        acceptance_criteria=["It must work"],
    )
    adapter = DoerAdapter()
    prompt = adapter.build_prompt(task, TaskContext(task=task, prior_artifacts={}, rework_count=0))
    assert "It must work" in prompt


def test_checker_build_prompt_includes_diff(task, ctx):
    ctx_with_diff = ctx.model_copy(update={"prior_artifacts": {"git_diff": "diff --git..."}})
    adapter = CheckerAdapter()
    prompt = adapter.build_prompt(task, ctx_with_diff)
    assert "diff" in prompt.lower()


def test_qa_adapter_parse_fail_with_source(fail_result, task, ctx):
    adapter = QaAutomationAdapter()
    out = adapter.parse_output(fail_result)
    assert out.status == "fail"
    assert out.failure_source == "broken_implementation"


def test_generic_parse_output_pass(pass_result, task, ctx):
    for AdapterCls in (PlannerAdapter, DoerAdapter, CheckerAdapter, TesterAdapter, LessonsAdapter):
        adapter = AdapterCls()
        out = adapter.parse_output(pass_result)
        assert out.status == "pass"
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/agent_adapters/test_role_adapters.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement all six adapters**

```python
# system/orchestrator/agent_adapters/planner.py
from __future__ import annotations
import json
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class PlannerAdapter(AgentAdapter):
    role = "planner"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return (
            self._load_template()
            + f"\n\n## Task Envelope\n"
            + f"task_id: {task.task_id}\ntitle: {task.title}\n"
            + f"description: {task.description}\n"
            + f"acceptance_criteria:\n" + "\n".join(f"  - {c}" for c in task.acceptance_criteria)
        )

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
```

```python
# system/orchestrator/agent_adapters/doer.py
from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class DoerAdapter(AgentAdapter):
    role = "doer"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        parts = [self._load_template(), f"\n\n## Task: {task.task_id} — {task.title}"]
        if task.acceptance_criteria:
            parts.append("\n## Acceptance Criteria")
            parts.extend(f"- {c}" for c in task.acceptance_criteria)
        if context.rework_count > 0 and context.failure_notes:
            parts.append(f"\n## Rework Notes (iteration {context.rework_count})")
            parts.append(context.failure_notes)
        return "\n".join(parts)

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
```

```python
# system/orchestrator/agent_adapters/checker.py
from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class CheckerAdapter(AgentAdapter):
    role = "checker"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        parts = [self._load_template(), f"\n\n## Task: {task.task_id}"]
        if "git_diff" in context.prior_artifacts:
            parts.append("\n## Git Diff\n```diff\n" + context.prior_artifacts["git_diff"] + "\n```")
        if "doer_report" in context.prior_artifacts:
            parts.append("\n## Doer Report\n" + context.prior_artifacts["doer_report"])
        return "\n".join(parts)

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
```

```python
# system/orchestrator/agent_adapters/tester.py
from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class TesterAdapter(AgentAdapter):
    role = "tester"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return self._load_template() + f"\n\n## Task: {task.task_id} — {task.title}"

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
```

```python
# system/orchestrator/agent_adapters/qa_automation.py
from __future__ import annotations
import json
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class QaAutomationAdapter(AgentAdapter):
    role = "qa_automation"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return self._load_template() + f"\n\n## Task: {task.task_id} — {task.title}"

    def parse_output(self, result: RunResult) -> ParsedOutput:
        try:
            data = json.loads(result.output)
            return ParsedOutput(
                status=data.get("status", "fail"),
                artifact_paths=[],
                failure_source=data.get("failure_source"),
                notes=data.get("notes", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return ParsedOutput(status="fail", artifact_paths=[], notes=result.output[:200])
```

```python
# system/orchestrator/agent_adapters/lessons.py
from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class LessonsAdapter(AgentAdapter):
    role = "lessons"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        parts = [self._load_template(), f"\n\n## Task: {task.task_id} — {task.title}"]
        for name, path in context.prior_artifacts.items():
            parts.append(f"\n## Artifact: {name}\nPath: {path}")
        return "\n".join(parts)

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
```

Add shared `_parse_generic` helper to `base.py` (append):

```python
# append to system/orchestrator/agent_adapters/base.py
import json as _json

def _parse_generic(result: RunResult) -> ParsedOutput:
    """Default parse: look for {status: pass/fail} JSON in output."""
    try:
        data = _json.loads(result.output)
        return ParsedOutput(
            status=data.get("status", "fail"),
            artifact_paths=data.get("artifact_paths", []),
            notes=data.get("notes", ""),
        )
    except (_json.JSONDecodeError, KeyError):
        status = "pass" if result.exit_code == 0 else "fail"
        return ParsedOutput(status=status, artifact_paths=[], notes=result.output[:200])
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/agent_adapters/ -v
```
Expected: all PASSED.

- [ ] **Step 5: Populate agent_adapters/__init__.py**

```python
# system/orchestrator/agent_adapters/__init__.py
from .base import AgentAdapter, TaskContext
from .planner import PlannerAdapter
from .doer import DoerAdapter
from .checker import CheckerAdapter
from .tester import TesterAdapter
from .qa_automation import QaAutomationAdapter
from .lessons import LessonsAdapter

__all__ = [
    "AgentAdapter", "TaskContext",
    "PlannerAdapter", "DoerAdapter", "CheckerAdapter",
    "TesterAdapter", "QaAutomationAdapter", "LessonsAdapter",
]
```

- [ ] **Step 6: Commit**

```bash
git add system/orchestrator/agent_adapters/ \
  tests/unit/orchestrator/agent_adapters/test_role_adapters.py
git commit -m "feat: add six role adapters (planner, doer, checker, tester, qa, lessons)"
```

---

### Task 22: Router

**Files:**
- Create: `system/orchestrator/router.py`
- Create: `tests/unit/orchestrator/test_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_router.py
import pytest
from system.orchestrator.router import Router
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.agent_adapters.checker import CheckerAdapter
import yaml, textwrap


CONFIG_YAML = textwrap.dedent("""\
    github:
      repo: owner/repo
    agent_defaults:
      planner: claude
      doer: claude
      checker: codex
      tester: gemini
      qa_automation: claude
      lessons: claude
    routing_rules:
      feature:
        backend:
          doer: qwen
          checker: codex
      refactor:
        service:
          doer: claude
""")


@pytest.fixture
def router():
    cfg = OrchestratorConfig.model_validate(yaml.safe_load(CONFIG_YAML))
    return Router(config=cfg)


def test_router_feature_backend_doer_is_qwen(router):
    runner, adapter = router.resolve("feature", "backend", "doer")
    assert isinstance(runner, QwenRunner)
    assert isinstance(adapter, DoerAdapter)


def test_router_feature_backend_checker_is_codex(router):
    runner, adapter = router.resolve("feature", "backend", "checker")
    assert isinstance(runner, CodexRunner)
    assert isinstance(adapter, CheckerAdapter)


def test_router_falls_back_to_defaults(router):
    # "bug" not in routing_rules → falls back to agent_defaults
    runner, adapter = router.resolve("bug", "frontend", "doer")
    assert isinstance(runner, ClaudeRunner)   # agent_defaults.doer = claude


def test_router_tester_from_defaults(router):
    runner, _ = router.resolve("feature", "unknown-component", "tester")
    assert isinstance(runner, GeminiRunner)   # agent_defaults.tester = gemini


def test_router_unknown_role_raises(router):
    with pytest.raises(ValueError, match="Unknown role"):
        router.resolve("feature", "backend", "unknown_role")
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_router.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# system/orchestrator/router.py
from __future__ import annotations
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.copilot_runner import CopilotRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.agent_adapters.base import AgentAdapter
from system.orchestrator.agent_adapters.planner import PlannerAdapter
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.agent_adapters.checker import CheckerAdapter
from system.orchestrator.agent_adapters.tester import TesterAdapter
from system.orchestrator.agent_adapters.qa_automation import QaAutomationAdapter
from system.orchestrator.agent_adapters.lessons import LessonsAdapter

_RUNNERS: dict[str, type[AgentRunner]] = {
    "claude": ClaudeRunner,
    "codex": CodexRunner,
    "gemini": GeminiRunner,
    "copilot": CopilotRunner,
    "qwen": QwenRunner,
}

_ADAPTERS: dict[str, type[AgentAdapter]] = {
    "planner": PlannerAdapter,
    "doer": DoerAdapter,
    "checker": CheckerAdapter,
    "tester": TesterAdapter,
    "qa_automation": QaAutomationAdapter,
    "lessons": LessonsAdapter,
}


class Router:
    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    def resolve(
        self, task_type: str, component: str, role: str
    ) -> tuple[AgentRunner, AgentAdapter]:
        if role not in _ADAPTERS:
            raise ValueError(f"Unknown role: {role}")
        agent_type = (
            self._config.routing_rules
            .get(task_type, {})
            .get(component, {})
            .get(role)
            or self._config.agent_defaults.get(role, "claude")
        )
        runner_cls = _RUNNERS.get(agent_type, ClaudeRunner)
        adapter_cls = _ADAPTERS[role]
        return runner_cls(), adapter_cls()
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_router.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/router.py tests/unit/orchestrator/test_router.py
git commit -m "feat: add Router ((task_type, component, role) → runner + adapter)"
```

---

## Chunk 4: Orchestrator Loop, CLI, TUI, Integration Test

### Task 23: Orchestrator loop (core logic)

**Files:**
- Create: `system/orchestrator/orchestrator.py`
- Create: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_orchestrator_loop.py
import queue
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import Task, TaskState, ConcreteStateMachine
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult


@pytest.fixture
def task_env():
    return TaskEnvelope(task_id="BRQ-1", title="Test", task_type="feature", component="backend")


@pytest.fixture
def loop(tmp_path):
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    event_queue: queue.Queue = queue.Queue()
    return OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log,
        event_queue=event_queue,
    )


def test_loop_advances_new_task_with_no_deps(loop):
    # Task envelope present, dependencies list is empty → gate passes
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature",
                       component="backend", dependencies=[])
    result = loop.check_dependency_gate(task, all_tasks={"BRQ-1": (task, env)})
    assert result is True


def test_loop_holds_task_with_unmet_deps(loop):
    task = Task(task_id="BRQ-2", state=TaskState.NEW)
    dep_task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env_brq1 = TaskEnvelope(task_id="BRQ-1", title="dep", task_type="feature", component="backend")
    env_brq2 = TaskEnvelope(task_id="BRQ-2", title="t", task_type="feature",
                             component="backend", dependencies=["BRQ-1"])
    all_tasks = {
        "BRQ-1": (dep_task, env_brq1),
        "BRQ-2": (task, env_brq2),
    }
    result = loop.check_dependency_gate(task, all_tasks=all_tasks)
    assert result is False


def test_loop_dep_gate_passes_when_dep_done(loop):
    task = Task(task_id="BRQ-2", state=TaskState.NEW)
    dep_task = Task(task_id="BRQ-1", state=TaskState.DONE)
    env_brq1 = TaskEnvelope(task_id="BRQ-1", title="dep", task_type="feature", component="backend")
    env_brq2 = TaskEnvelope(task_id="BRQ-2", title="t", task_type="feature",
                             component="backend", dependencies=["BRQ-1"])
    all_tasks = {
        "BRQ-1": (dep_task, env_brq1),
        "BRQ-2": (task, env_brq2),
    }
    result = loop.check_dependency_gate(task, all_tasks=all_tasks)
    assert result is True


def test_merge_readiness_check_pass(loop, task_env, tmp_path):
    store = loop._artifact_store
    from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
    artifact = MergeReadinessArtifact(
        task_id="BRQ-1",
        checked_at="2026-03-14T14:00:00Z",
        artifacts_present=["task-envelope", "doer-report"],
        branch="feat/BRQ-1-test",
        merge_target="dev",
        ci_conclusion="success",
        branch_is_current=True,
        verdict="pass",
    )
    store.write("BRQ-1", "merge-readiness", artifact)
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW)
    result = loop.check_merge_readiness(task, branch="feat/BRQ-1-test")
    assert result is True


def test_merge_readiness_check_missing(loop, task_env):
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW)
    result = loop.check_merge_readiness(task, branch="feat/BRQ-1-test")
    assert result is False
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement OrchestratorLoop**

```python
# system/orchestrator/orchestrator.py
from __future__ import annotations
import queue
import threading
import time
from pathlib import Path
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.event_log import EventLog
from system.orchestrator.router import Router
from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState


class OrchestratorLoop:
    def __init__(
        self,
        config: OrchestratorConfig,
        state_machine: ConcreteStateMachine,
        artifact_store: ArtifactStore,
        event_log: EventLog,
        event_queue: queue.Queue,
    ) -> None:
        self._config = config
        self._sm = state_machine
        self._artifact_store = artifact_store
        self._log = event_log
        self._queue = event_queue
        self._stop_event = threading.Event()
        self._router = Router(config=config)
        self._current_process: "subprocess.Popen | None" = None   # set by runner layer

    def stop(self) -> None:
        self._stop_event.set()

    def force_kill_current(self) -> None:
        """Force-terminate any in-flight runner subprocess (spec section 10 step c)."""
        import subprocess as _sp
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()
            try:
                self._current_process.wait(timeout=5)
            except _sp.TimeoutExpired:
                self._current_process.kill()

    def flush(self, config: "OrchestratorConfig") -> None:
        """Flush event log and write runtime-state.yaml (spec section 10 steps d+e)."""
        import yaml as _yaml
        import datetime
        state_path = Path(config.orchestrator.runtime_state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(_yaml.dump({
            "shutdown_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "note": "graceful shutdown",
        }))

    def check_dependency_gate(
        self,
        task: Task,
        all_tasks: dict[str, tuple[Task, TaskEnvelope]],
    ) -> bool:
        """Return True if all dependencies are in DONE state."""
        env = all_tasks.get(task.task_id)
        if env is None:
            return True   # no envelope context → assume no deps
        _, task_env = env
        for dep_id in task_env.dependencies:
            dep = all_tasks.get(dep_id)
            if dep is None or dep[0].state != TaskState.DONE:
                return False
        return True

    def check_merge_readiness(self, task: Task, branch: str) -> bool:
        """Deterministic merge-readiness check. Returns True iff artifact exists with verdict=pass."""
        artifact = self._artifact_store.read(task.task_id, "merge-readiness", MergeReadinessArtifact)
        return artifact is not None and artifact.verdict == "pass"

    def _emit(self, event: OrchestratorEvent) -> None:
        self._log.append(event)
        self._queue.put_nowait(event)

    def run(
        self,
        tasks: list[tuple[Task, TaskEnvelope]],
    ) -> None:
        """Main loop — processes tasks until stop() is called."""
        all_tasks = {t.task_id: (t, env) for t, env in tasks}
        while not self._stop_event.is_set():
            for task_id, (task, env) in list(all_tasks.items()):
                task = self._tick(task, env, all_tasks)
                all_tasks[task_id] = (task, env)
            time.sleep(self._config.orchestrator.poll_interval_seconds)

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
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat: add OrchestratorLoop core (dep gate, merge-readiness check, event emit)"
```

---

### Task 24: main.py CLI entry point

**Files:**
- Create: `system/orchestrator/main.py`

- [ ] **Step 1: Implement main.py (no separate tests — covered by integration test)**

```python
# system/orchestrator/main.py
"""
Orchestrator entry point.

Usage:
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml
    python -m system.orchestrator.main --config system/orchestrator/orchestrator.yaml --no-tui
"""
from __future__ import annotations
import argparse
import queue
import signal
import sys
import threading
from pathlib import Path
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.config import load_config
from system.orchestrator.event_log import EventLog
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import ConcreteStateMachine
from system.orchestrator.task_loader import CompositeTaskLoader
from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader
from system.orchestrator.state_machine import Task, TaskState


def _build_loop(cfg_path: Path) -> tuple[OrchestratorLoop, queue.Queue, OrchestratorConfig]:
    cfg = load_config(cfg_path)
    sm = ConcreteStateMachine(
        max_rework_loops=cfg.orchestrator.max_rework_loops,
        max_retries=cfg.orchestrator.max_retries,
    )
    store = ArtifactStore(base=Path(cfg.orchestrator.artifact_base))
    log = EventLog(path=Path(cfg.orchestrator.event_log))
    eq: queue.Queue = queue.Queue(maxsize=1000)
    loop = OrchestratorLoop(
        config=cfg,
        state_machine=sm,
        artifact_store=store,
        event_log=log,
        event_queue=eq,
    )
    return loop, eq, cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Breqy Orchestrator")
    parser.add_argument("--config", default="system/orchestrator/orchestrator.yaml",
                        help="Path to orchestrator.yaml")
    parser.add_argument("--no-tui", action="store_true", help="Run without TUI")
    args = parser.parse_args()

    loop, eq, cfg = _build_loop(Path(args.config))

    # Load tasks
    github_loader = GitHubTaskLoader(
        repo=cfg.github.repo, managed_label=cfg.github.managed_label
    )
    local_loader = LocalYamlTaskLoader(tasks_dir=Path(cfg.orchestrator.task_fallback_dir))
    composite = CompositeTaskLoader(github=github_loader, local=local_loader)
    envelopes = composite.load_pending()
    tasks = [(Task(task_id=env.task_id, state=TaskState.NEW), env) for env in envelopes]

    # Start orchestrator loop in background thread
    loop_thread = threading.Thread(
        target=loop.run, args=(tasks,), daemon=True, name="orchestrator-loop"
    )
    loop_thread.start()

    signal.signal(signal.SIGINT, lambda s, f: None)   # register early
    signal.signal(signal.SIGTERM, lambda s, f: None)

    def _shutdown(signum, frame):
        print("\n[orchestrator] Shutdown requested — waiting for current step...")
        loop.stop()
        loop_thread.join(timeout=30)
        # Force-terminate any runner subprocess still alive after timeout
        if loop_thread.is_alive():
            loop.force_kill_current()
        # Flush event log and persist runtime state (spec section 10 steps d+e)
        loop.flush(cfg)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if args.no_tui:
        loop_thread.join()
        return

    # Launch TUI (blocks main thread)
    from system.orchestrator.tui.app import OrchestratorApp
    app = OrchestratorApp(event_queue=eq, tasks=tasks)
    app.run()
    loop.stop()
    loop_thread.join(timeout=30)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
python -c "from system.orchestrator.main import main; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add system/orchestrator/main.py
git commit -m "feat: add orchestrator CLI entry point (main.py)"
```

---

### Task 25: TUI — App + PipelinePanel + TaskPanel

**Files:**
- Create: `system/orchestrator/tui/app.py`
- Create: `system/orchestrator/tui/panels/pipeline_panel.py`
- Create: `system/orchestrator/tui/panels/task_panel.py`
- Create: `tests/unit/orchestrator/test_tui_app.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/orchestrator/test_tui_app.py
import queue
import pytest
from system.orchestrator.tui.app import OrchestratorApp
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope


def test_app_instantiates():
    eq: queue.Queue = queue.Queue()
    env = TaskEnvelope(task_id="BRQ-1", title="Test", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    app = OrchestratorApp(event_queue=eq, tasks=[(task, env)])
    assert app is not None
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_tui_app.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement app.py**

```python
# system/orchestrator/tui/app.py
from __future__ import annotations
import queue
import threading
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Horizontal, Vertical
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.tui.panels.pipeline_panel import PipelinePanel
from system.orchestrator.tui.panels.task_panel import TaskPanel
from system.orchestrator.tui.panels.agent_panel import AgentPanel
from system.orchestrator.tui.panels.log_panel import LogPanel


class OrchestratorApp(App):
    CSS = """
    #top { height: 60%; }
    #pipeline { width: 35%; border: solid green; }
    #task { width: 65%; border: solid blue; }
    #agent { height: 25%; border: solid yellow; }
    #log { height: 15%; border: solid gray; }
    """

    def __init__(self, event_queue: queue.Queue, tasks: list[tuple[Task, TaskEnvelope]]) -> None:
        super().__init__()
        self._queue = event_queue
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="top"):
                yield PipelinePanel(id="pipeline")
                yield TaskPanel(tasks=self._tasks, id="task")
            yield AgentPanel(id="agent")
            yield LogPanel(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.5, self._poll_queue)

    def _poll_queue(self) -> None:
        while True:
            try:
                event: OrchestratorEvent = self._queue.get_nowait()
                self.query_one(PipelinePanel).handle_event(event)
                self.query_one(TaskPanel).handle_event(event)
                self.query_one(AgentPanel).handle_event(event)
                self.query_one(LogPanel).handle_event(event)
            except queue.Empty:
                break
```

- [ ] **Step 4: Implement PipelinePanel**

```python
# system/orchestrator/tui/panels/pipeline_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import Static
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import TaskState

_STATE_ORDER = list(TaskState)


class PipelinePanel(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._completed: set[str] = set()
        self._current: str | None = None

    def compose(self):
        for state in _STATE_ORDER:
            yield Static(f"○ {state.value}", id=f"state-{state.value}")

    def handle_event(self, event: OrchestratorEvent) -> None:
        if event.event_type == "state_transition" and event.to_state:
            if self._current is not None:
                self._completed.add(self._current)
            self._current = event.to_state
            for state in _STATE_ORDER:
                if state.value in self._completed:
                    label = "✓"
                elif state.value == self._current:
                    label = "●"
                else:
                    label = "○"
                try:
                    widget = self.query_one(f"#state-{state.value}", Static)
                    widget.update(f"{label} {state.value}")
                except Exception:
                    pass
```

- [ ] **Step 5: Implement TaskPanel**

```python
# system/orchestrator/tui/panels/task_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import Static
from system.orchestrator.schemas.events import OrchestratorEvent
from system.orchestrator.state_machine import Task, TaskState
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class TaskPanel(Widget):
    def __init__(self, tasks: list[tuple[Task, TaskEnvelope]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._tasks = {t.task_id: (t, env) for t, env in tasks}
        self._active_id: str | None = tasks[0][0].task_id if tasks else None

    def compose(self):
        yield Static("No active task", id="task-info")

    def handle_event(self, event: OrchestratorEvent) -> None:
        self._active_id = event.task_id
        task, env = self._tasks.get(event.task_id, (None, None))
        if task and env:
            info = (
                f"ID:     {env.task_id}\n"
                f"Title:  {env.title}\n"
                f"Type:   {env.task_type} / {env.component}\n"
                f"State:  {event.to_state or task.state.value}\n"
                f"Role:   {event.role or '—'}\n"
                f"Agent:  {event.agent_type or '—'}\n"
                f"Rework: {task.rework_count} / 3\n"
                f"Branch: {task.branch or '—'}\n"
                f"PR:     {task.pr_url or '—'}"
            )
            try:
                self.query_one("#task-info", Static).update(info)
            except Exception:
                pass
```

- [ ] **Step 6: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_tui_app.py -v
```
Expected: 1 PASSED.

- [ ] **Step 7: Commit**

```bash
git add system/orchestrator/tui/ tests/unit/orchestrator/test_tui_app.py
git commit -m "feat: add TUI app with PipelinePanel and TaskPanel"
```

---

### Task 26: AgentPanel + LogPanel

**Files:**
- Create: `system/orchestrator/tui/panels/agent_panel.py`
- Create: `system/orchestrator/tui/panels/log_panel.py`

- [ ] **Step 1: Implement AgentPanel**

```python
# system/orchestrator/tui/panels/agent_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import RichLog
from system.orchestrator.schemas.events import OrchestratorEvent


class AgentPanel(Widget):
    MAX_LINES = 50

    def compose(self):
        yield RichLog(id="agent-log", markup=True)

    def handle_event(self, event: OrchestratorEvent) -> None:
        if event.event_type in ("agent_spawn", "agent_complete"):
            try:
                log = self.query_one("#agent-log", RichLog)
                prefix = f"[{event.role}/{event.agent_type}]" if event.role else "[orchestrator]"
                log.write(f"{prefix} {event.notes}")
            except Exception:
                pass
```

- [ ] **Step 2: Implement LogPanel**

```python
# system/orchestrator/tui/panels/log_panel.py
from __future__ import annotations
from textual.widget import Widget
from textual.widgets import RichLog
from system.orchestrator.schemas.events import OrchestratorEvent

_COLOURS = {
    "state_transition": "green",
    "agent_spawn": "cyan",
    "agent_complete": "blue",
    "error": "red",
    "blocked": "red",
    "rate_limit": "yellow",
    "ci_result": "magenta",
}


class LogPanel(Widget):
    def compose(self):
        yield RichLog(id="event-log", markup=True)

    def handle_event(self, event: OrchestratorEvent) -> None:
        colour = _COLOURS.get(event.event_type, "white")
        ts = event.timestamp[11:19]   # HH:MM:SS
        msg = f"[{colour}]{ts}  {event.event_type:<22} {event.task_id}  {event.notes[:50]}[/{colour}]"
        try:
            self.query_one("#event-log", RichLog).write(msg)
        except Exception:
            pass
```

- [ ] **Step 3: Commit**

```bash
git add system/orchestrator/tui/panels/agent_panel.py \
  system/orchestrator/tui/panels/log_panel.py
git commit -m "feat: add AgentPanel and LogPanel TUI widgets"
```

---

### Task 27: Integration test — local YAML task through full loop

**Files:**
- Create: `tests/integration/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/orchestrator/test_orchestrator_loop.py
"""
Integration test: feed a local YAML task into the orchestrator loop.
Runners are mocked so no AI providers are needed.
Verifies: task loads → dep gate → NEW→SHAPING state transition → event emitted.
"""
import queue
import threading
import time
import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch
from system.orchestrator.config import OrchestratorConfig, GitHubConfig, OrchestratorSettings
from system.orchestrator.orchestrator import OrchestratorLoop
from system.orchestrator.state_machine import ConcreteStateMachine, Task, TaskState
from system.orchestrator.artifact_store import ArtifactStore
from system.orchestrator.event_log import EventLog
from system.orchestrator.local_task_loader import LocalYamlTaskLoader
from system.orchestrator.schemas.task_envelope import TaskEnvelope


TASK_YAML = {
    "task_id": "INT-1",
    "title": "Integration test task",
    "task_type": "feature",
    "component": "backend",
}


@pytest.fixture
def tmp_dirs(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "INT-1.yaml").write_text(yaml.dump(TASK_YAML))
    return tmp_path, tasks_dir


def test_new_task_transitions_to_shaping(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        orchestrator=OrchestratorSettings(poll_interval_seconds=0),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()

    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log, event_queue=eq,
    )

    # Load task
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    envelopes = loader.load_pending()
    assert len(envelopes) == 1
    tasks = [(Task(task_id=env.task_id, state=TaskState.NEW), env) for env in envelopes]

    # Run one tick
    task, env = tasks[0]
    updated_task = loop._tick(task, env, {task.task_id: (task, env)})

    # Task should have advanced to READY_FOR_SHAPING
    assert updated_task.state == TaskState.READY_FOR_SHAPING

    # Event should be in queue
    assert not eq.empty()
    event = eq.get_nowait()
    assert event.event_type == "state_transition"
    assert event.to_state == "READY_FOR_SHAPING"
    assert event.task_id == "INT-1"

    # Event should be in JSONL log
    events = log.tail(1)
    assert len(events) == 1
    assert events[0].to_state == "READY_FOR_SHAPING"
```

- [ ] **Step 2: Run integration test**

```bash
pytest tests/integration/orchestrator/test_orchestrator_loop.py -v
```
Expected: 1 PASSED.

- [ ] **Step 3: Run full test suite to verify nothing broken**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass. Check coverage:

```bash
pytest tests/ --cov=system/orchestrator --cov-report=term-missing
```
Expected: ≥80% overall.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/orchestrator/test_orchestrator_loop.py
git commit -m "test: add integration test for orchestrator loop (NEW → READY_FOR_SHAPING)"
```

---

### Task 28: Add pyproject.toml entry point + final coverage check

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add CLI entry point**

Add to `[project.scripts]` in `pyproject.toml`:
```toml
[project.scripts]
breqy-orchestrator = "system.orchestrator.main:main"
```

- [ ] **Step 2: Sync and verify entry point**

```bash
uv sync
breqy-orchestrator --help
```
Expected: prints usage with `--config` and `--no-tui` options.

- [ ] **Step 3: Final coverage check**

```bash
pytest tests/unit/orchestrator/ --cov=system/orchestrator \
  --cov-report=term-missing --cov-fail-under=80
```
Expected: passes ≥80% coverage threshold.

- [ ] **Step 4: Run mypy and ruff**

```bash
ruff check system/orchestrator/
mypy system/orchestrator/
```
Expected: no errors.

- [ ] **Step 5: Final commit**

```bash
git add pyproject.toml
git commit -m "chore: add breqy-orchestrator CLI entry point"
```

---


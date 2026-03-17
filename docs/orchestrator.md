# Breqy Orchestrator — Complete Guide

The **Orchestrator** is Breqy's Phase 2 delivery workflow engine. It manages the lifecycle of shaped tasks from creation through completion, routing them through 6 AI agent roles, enforcing state machine guards, and emitting events for observability.

---

## Quick Start

### Prerequisites

- Python 3.12+
- GitHub account with a repo for task management
- API keys: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `DASHSCOPE_API_KEY`
- `uv` package manager

### Installation & Setup

```bash
cd /home/andrey/projects/breqy

# Install dependencies
uv sync

# Configure orchestrator
cp system/orchestrator/orchestrator.yaml system/orchestrator/orchestrator.yaml.local
# Edit orchestrator.yaml.local with your GitHub repo
```

### Start the Orchestrator

**With TUI (visual dashboard):**
```bash
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local
```

**Without TUI (CLI only):**
```bash
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local --no-tui
```

**Shutdown gracefully:** Press `Ctrl+C` — the orchestrator will:
1. Stop accepting new tasks
2. Wait for current agent to complete (up to 30s)
3. Force-kill any runaway subprocesses
4. Flush event log and persist runtime state

---

## Architecture

### High-Level Flow

```
Tasks (GitHub Issues or YAML)
    ↓
[Orchestrator Loop]
    • Load pending tasks
    • Check dependency gates
    • Transition states
    • Emit events
    ↓
[Router] → [Agent Runner] → [Agent Adapter] → Subprocess (Claude CLI, Codex, etc.)
    ↓
[Event Queue] ← [Event Log]
    ↓
[TUI Dashboard] (monitors pipeline, task state, agent logs, event history)
```

### Components

#### **OrchestratorLoop** (`system/orchestrator/orchestrator.py`)
- Main loop that polls tasks and advances state
- Checks dependency gates before NEW→READY_FOR_SHAPING transition
- Checks merge-readiness before READY_FOR_MERGE_REVIEW→MERGED transition
- Emits `OrchestratorEvent` to log and queue
- Runs in background thread; TUI runs in main thread

#### **State Machine** (`system/orchestrator/state_machine.py`)
- 18 states: `NEW` → `DONE` (or `BLOCKED` on exhausted retries/rework)
- Guards on transitions: rework loops (max 3), retries (max 3)
- Blocks unconditional on `FAILED` → `READY_FOR_REWORK` if counter exceeded

#### **Router** (`system/orchestrator/router.py`)
- Maps `(task_type, component, role)` → `(AgentRunner, AgentAdapter)`
- **Task types:** `feature`, `bug`, `refactor`, `hotfix`
- **Components:** any string (e.g., `backend`, `tui`, `service`)
- **Roles:** `planner`, `doer`, `checker`, `tester`, `qa_automation`, `lessons`
- Routing rules in `orchestrator.yaml` override agent defaults

#### **Agent Runners** (`system/orchestrator/runners/`)
- `ClaudeRunner` — wraps `claude` CLI subprocess
- `CodexRunner` — wraps `codex` CLI subprocess
- `GeminiRunner` — wraps `gemini` CLI subprocess
- `CopilotRunner` — wraps `gh copilot suggest` command
- `QwenRunner` — wraps `qwen` CLI subprocess

Each runner:
- Spawns subprocess with prompt passed via stdin
- Polls stdout for AI output
- Detects rate-limit keywords; returns `RunResult(status="rate_limited", session_id=...)`
- Supports session resumption with `--resume <session_id>` for Claude only

#### **Agent Adapters** (`system/orchestrator/agent_adapters/`)
- **PlannerAdapter** — parses task outline, dependencies, acceptance criteria
- **DoerAdapter** — parses implementation output, artifacts
- **CheckerAdapter** — parses code review findings
- **TesterAdapter** — parses test results (pass/fail/tests_run/tests_failed)
- **QaAutomationAdapter** — parses automation test results + failure source
- **LessonsAdapter** — parses lessons learned + instruction update proposals

Each adapter:
- Loads role-specific prompt template from `system/orchestrator/prompts/{role}.md`
- Builds prompt with task envelope + prior artifacts + context
- Parses runner output into structured `ParsedOutput` artifact

#### **Artifact Store** (`system/orchestrator/artifact_store.py`)
- Writes Pydantic models as JSON; strings as Markdown
- Path: `ai-artifacts/{task_id}/{name}.json` or `.md`
- Read/write/exists operations with schema validation

#### **Event Log** (`system/orchestrator/event_log.py`)
- Append-only JSONL file at `.breqy/orchestrator/events.jsonl`
- Records every state transition, agent spawn, rate limit, error
- `tail(n)` retrieves last N events

#### **TUI** (`system/orchestrator/tui/`)
- **PipelinePanel** — visualizes state transitions (○ pending → ● current → ✓ done)
- **TaskPanel** — shows active task ID, title, type, component, role, agent, rework count, branch, PR
- **AgentPanel** — logs agent spawn/complete events with role/agent type
- **LogPanel** — color-coded event history (green=transition, cyan=spawn, blue=complete, red=error, yellow=rate_limit, magenta=ci)

---

## Configuration

### `orchestrator.yaml` Structure

```yaml
github:
  repo: owner/repo              # GitHub repo (owner/name)
  managed_label: orchestrator:managed
  ci_timeout_minutes: 30        # GitHub Actions timeout
  ci_poll_interval_seconds: 60  # How often to check CI status

orchestrator:
  poll_interval_seconds: 30     # Loop tick frequency
  max_rework_loops: 3           # Max rework count before BLOCKED
  max_retries: 3                # Max retry count before BLOCKED
  retry_backoff_seconds: 60     # Wait before retrying
  artifact_base: ai-artifacts   # Artifact directory
  event_log: .breqy/orchestrator/events.jsonl
  runtime_state: .breqy/orchestrator/runtime-state.yaml
  task_fallback_dir: system/orchestrator/tasks
  branch_stale_days: 3

agent_defaults:                 # Default agent for each role
  planner: claude
  doer: claude
  checker: codex
  tester: gemini
  qa_automation: claude
  lessons: claude

routing_rules:                  # Override defaults: (task_type, component, role) → agent
  feature:
    backend:
      planner: claude
      doer: claude
      checker: codex
      tester: gemini
      qa_automation: claude
      lessons: claude
    tui:
      planner: claude
      doer: claude
      checker: qwen
      tester: gemini
      qa_automation: gemini
      lessons: claude
  bug:
    low_risk:
      doer: copilot
      checker: codex
      tester: gemini
      lessons: claude
  refactor:
    service:
      doer: qwen
      checker: codex
      tester: gemini
      lessons: claude
```

### Environment Variables

Create `.env` in project root (see `.env.sample`):
```bash
GITHUB_TOKEN=ghp_...           # GitHub API token
ANTHROPIC_API_KEY=sk-...       # Claude API key
OPENAI_API_KEY=sk-...          # OpenAI/Codex key
GOOGLE_API_KEY=...             # Gemini API key
DASHSCOPE_API_KEY=...          # Qwen API key
GITHUB_COPILOT_TOKEN=...       # GitHub Copilot token (if using CopilotRunner)
```

---

## Task Lifecycle

### TaskEnvelope Schema

Every task is described by a `TaskEnvelope`:

```python
from system.orchestrator.schemas.task_envelope import TaskEnvelope

env = TaskEnvelope(
    task_id="BRQ-144",
    title="Session resume flow",
    description="Allow resuming sessions after rate limit",
    task_type="feature",              # feature | bug | refactor | hotfix
    component="backend",               # e.g., backend, tui, service
    dependencies=["BRQ-100", "BRQ-101"],
    acceptance_criteria=["Sessions persist across restarts"],
    test_hints=["Test with mock rate limit response"],
    priority="high",                   # medium (default) | low | high
    labels=["orchestrator:managed"],
    github_issue_number=144,
)
```

### State Machine (18 States)

```
NEW
  ↓ [dep gate passes]
READY_FOR_SHAPING
  ↓ [planner completes]
SHAPING_IN_PROGRESS
  ↓ [planner task envelope + plan written]
READY_FOR_PLANNING_REVIEW
  ↓ [checker approves plan]
PLANNING_REVIEW_PASSED
  ↓ [doer starts]
READY_FOR_DOER
  ↓ [doer starts]
DOER_IN_PROGRESS
  ↓ [doer completes]
READY_FOR_CODE_REVIEW
  ↓ [checker starts]
CODE_REVIEW_IN_PROGRESS
  ↓ [checker completes]
REVIEW_PASSED / READY_FOR_REWORK (if issues found)
  ↓ (repeat rework loop up to 3 times)
  ↓ [doer rework completes]
READY_FOR_TESTING
  ↓ [tester starts]
TESTING_IN_PROGRESS
  ↓ [tester completes]
TEST_PASSED / READY_FOR_RETRY (if tests fail)
  ↓ (repeat retry loop up to 3 times)
  ↓ [doer fixes & tester re-runs]
READY_FOR_QA
  ↓ [qa_automation starts]
QA_IN_PROGRESS
  ↓ [qa_automation completes]
QA_PASSED / READY_FOR_QA_RETRY (if automation fails)
  ↓ (repeat qa retry loop)
  ↓ [qa_automation re-runs]
READY_FOR_MERGE_REVIEW
  ↓ [merge-readiness check: CI green, artifacts present, branch current]
READY_FOR_MERGE
  ↓ [GitHub merge (automated or manual)]
MERGED
  ↓
LESSONS_TRIGGERED
  ↓ [lessons agent extracts & records lessons]
DONE

BLOCKED (terminal, if max rework/retry/qa-retry exceeded)
FAILED (terminal, on unrecoverable error)
```

### Dependency Gate

Tasks with dependencies stay in `NEW` until **all dependencies are in `DONE` state**.

```python
# In orchestrator loop:
if loop.check_dependency_gate(task, all_tasks):
    # Advance to READY_FOR_SHAPING
else:
    # Emit "dependency_wait" event; stay in NEW
```

### Rate Limiting

If a runner detects rate-limit keywords (e.g., "rate_limited", "overloaded"), it returns:
```python
RunResult(status="rate_limited", session_id="sid-abc123", ...)
```

The orchestrator:
1. Stores session ID in task state
2. Polls `ccusage blocks --json` for window availability
3. On window open: resumes with `--resume sid-abc123`

---

## Agent Roles & Workflow

### 1. **Planner** (READY_FOR_SHAPING)
- **Input:** TaskEnvelope with title, description, acceptance criteria
- **Output:** ParsedOutput with status (pass/fail), artifact paths
- **Artifacts:** `{task_id}/shaped-task.json` — refined acceptance criteria, implementation plan, test strategy
- **Template:** `system/orchestrator/prompts/planner.md`

### 2. **Doer** (READY_FOR_DOER)
- **Input:** TaskEnvelope + shaped task + dependencies
- **Output:** ParsedOutput with artifact paths, optional session_id for rate limit
- **Artifacts:** `{task_id}/doer-report.json` — code changes, branch name, PR URL
- **Template:** `system/orchestrator/prompts/doer.md`

### 3. **Checker** (CODE_REVIEW_IN_PROGRESS)
- **Input:** TaskEnvelope + prior artifacts (doer report)
- **Output:** ParsedOutput with findings (code quality, style, design, best practices)
- **Artifacts:** `{task_id}/review.json` — findings list, summary, pass/fail
- **Template:** `system/orchestrator/prompts/checker.md`
- **Rework Loop:** On findings, doer is triggered for rework (max 3 loops)

### 4. **Tester** (TESTING_IN_PROGRESS)
- **Input:** TaskEnvelope + code changes (branch/PR)
- **Output:** ParsedOutput with tests_run, tests_failed, pass/fail status
- **Artifacts:** `{task_id}/test-results.json` — test count, pass/fail, output
- **Template:** `system/orchestrator/prompts/tester.md`
- **Retry Loop:** On test failure, doer fixes + tester re-runs (max 3 retries)

### 5. **QA Automation** (QA_IN_PROGRESS)
- **Input:** TaskEnvelope + artifacts from prior roles
- **Output:** ParsedOutput with failure_source (broken_implementation, broken_automation, ambiguous_criteria)
- **Artifacts:** `{task_id}/qa-results.json` — pass/fail, failure source, output
- **Template:** `system/orchestrator/prompts/qa_automation.md`
- **Retry Loop:** On failure, doer fixes + qa_automation re-runs

### 6. **Lessons** (LESSONS_TRIGGERED)
- **Input:** TaskEnvelope + all prior artifacts
- **Output:** ParsedOutput with lessons list, instruction_update_proposed flag
- **Artifacts:** `{task_id}/lessons.json` — lessons, instruction update proposal
- **Template:** `system/orchestrator/prompts/lessons.md`

---

## API & Event Types

### OrchestratorEvent

```python
from system.orchestrator.schemas.events import OrchestratorEvent

event = OrchestratorEvent(
    task_id="BRQ-144",
    event_type="state_transition",      # or: agent_spawn, agent_complete, error, blocked, rate_limit, ci_result, dependency_wait
    from_state="NEW",
    to_state="READY_FOR_SHAPING",
    role="planner",
    agent_type="claude",
    artifact_paths=["ai-artifacts/BRQ-144/shaped-task.json"],
    notes="Task envelope created with acceptance criteria",
)
```

**Event types:**
- `state_transition` — task moved to new state
- `agent_spawn` — agent role started
- `agent_complete` — agent role finished
- `error` — unrecoverable error (task → BLOCKED or FAILED)
- `blocked` — task blocked due to exhausted loops/retries
- `rate_limit` — rate-limit detected, waiting
- `ci_result` — CI run result (pass/fail)
- `dependency_wait` — task waiting for dependency

### RunResult

```python
from system.orchestrator.schemas.run_result import RunResult

result = RunResult(
    status="completed",                 # or: rate_limited, failed
    output="[Full stdout from agent]",
    exit_code=0,
    session_id=None,                    # Set if rate_limited
    artifacts_written=["doer-report.json"],
)
```

### ParsedOutput

```python
from system.orchestrator.schemas.artifacts import ParsedOutput

artifact = ParsedOutput(
    status="pass",                      # or: fail
    artifact_paths=["doer-report.json"],
    failure_source=None,                # if fail: "broken_implementation", "broken_automation", "ambiguous_criteria"
    notes="Implementation complete, all tests passing",
)
```

---

## Loading Tasks

### From GitHub Issues

Add `orchestrator:managed` label to issues. Issue body must contain YAML block:

```markdown
## Task

```yaml
task_id: BRQ-144
title: Session resume flow
description: Allow resuming sessions after rate limit
task_type: feature
component: backend
dependencies:
  - BRQ-100
  - BRQ-101
acceptance_criteria:
  - Sessions persist across restarts
test_hints:
  - Test with mock rate limit response
priority: high
```

The orchestrator:
1. Queries GitHub for issues with `orchestrator:managed` label
2. Extracts YAML from issue body
3. Creates `TaskEnvelope` from YAML

### From Local YAML

Place `.yaml` files in `system/orchestrator/tasks/`:

```yaml
# system/orchestrator/tasks/BRQ-144.yaml
task_id: BRQ-144
title: Session resume flow
task_type: feature
component: backend
dependencies:
  - BRQ-100
```

### Composite Loader

Default: GitHub primary (wins on same task_id), local fallback.

```python
from system.orchestrator.task_loader import CompositeTaskLoader
from system.orchestrator.github_task_loader import GitHubTaskLoader
from system.orchestrator.local_task_loader import LocalYamlTaskLoader

github = GitHubTaskLoader(repo="owner/repo", managed_label="orchestrator:managed")
local = LocalYamlTaskLoader(tasks_dir=Path("system/orchestrator/tasks"))
composite = CompositeTaskLoader(github=github, local=local)

envelopes = composite.load_pending()
```

---

## Running Tests

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/unit/orchestrator/

# Integration test
pytest tests/integration/orchestrator/

# With coverage
pytest tests/ --cov=system/orchestrator --cov-report=html

# Specific test
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_loop_advances_new_task_with_no_deps -v
```

**Coverage target:** ≥80%

---

## Troubleshooting

### "Config not found"
```bash
# Ensure orchestrator.yaml.local exists
cp system/orchestrator/orchestrator.yaml system/orchestrator/orchestrator.yaml.local
# Edit with your GitHub repo
```

### "rate_limited — waiting for window"
- The agent hit a rate limit (e.g., Claude API quota)
- Orchestrator is polling `ccusage blocks --json` for window availability
- Resume occurs automatically when window opens
- Check logs: `tail -f .breqy/orchestrator/events.jsonl`

### "Task stuck in NEW"
- Check dependencies: `grep "BRQ-100" .breqy/orchestrator/events.jsonl`
- Ensure all dependencies are in DONE state
- Check `dependency_wait` events for details

### "Tests failing"
```bash
# Run with verbose output
pytest tests/unit/orchestrator/test_orchestrator_loop.py -v -s

# Check specific test
pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_loop_dep_gate_passes_when_dep_done -vv
```

### "Ruff/Mypy errors"
```bash
# Fix ruff issues
ruff check system/orchestrator/ --fix

# Check mypy
mypy system/orchestrator/ --ignore-missing-imports
```

---

## Example: Running a Task End-to-End

### 1. Create Task

```yaml
# system/orchestrator/tasks/BRQ-1.yaml
task_id: BRQ-1
title: Add login endpoint
task_type: feature
component: backend
acceptance_criteria:
  - POST /auth/login accepts username + password
  - Returns JWT token on success
test_hints:
  - Test with valid and invalid credentials
```

### 2. Start Orchestrator

```bash
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local
```

### 3. Watch TUI

- **PipelinePanel** shows progression: NEW → READY_FOR_SHAPING → ... → DONE
- **TaskPanel** shows active task, current role, agent type
- **AgentPanel** shows agent spawn/complete logs
- **LogPanel** shows event history with timestamps

### 4. Monitor Event Log

```bash
tail -f .breqy/orchestrator/events.jsonl | jq '.'
```

### 5. Inspect Artifacts

```bash
# Task envelope created by planner
cat ai-artifacts/BRQ-1/shaped-task.json | jq '.'

# Code changes by doer
cat ai-artifacts/BRQ-1/doer-report.json | jq '.'

# Review findings
cat ai-artifacts/BRQ-1/review.json | jq '.'

# Test results
cat ai-artifacts/BRQ-1/test-results.json | jq '.'
```

### 6. On Completion

- Task → DONE state
- PR merged to target branch
- Lessons artifact written
- Task exits loop

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ OrchestratorApp (Textual TUI)                                   │
│  ┌─────────────┬──────────────┐                                 │
│  │ PipelinePanel│ TaskPanel    │                                 │
│  │ (○→●→✓)     │ (ID, State)  │                                 │
│  └─────────────┴──────────────┘                                 │
│  ┌────────────────────────────┐                                 │
│  │ AgentPanel (spawn/complete) │                                 │
│  └────────────────────────────┘                                 │
│  ┌────────────────────────────┐                                 │
│  │ LogPanel (event history)   │                                 │
│  └────────────────────────────┘                                 │
└──────────────────────────────────────────────────────────────────┘
           ↑ (polls every 0.5s)
           │ event_queue
           │
┌──────────────────────────────────────────────────────────────────┐
│ OrchestratorLoop (background thread)                             │
│  • Load tasks (GitHub or local YAML)                             │
│  • Poll every 30s (configurable)                                 │
│  • For each task:                                                │
│    - Check dependency gate                                        │
│    - Transition state (if guards pass)                            │
│    - Emit event to queue & log                                   │
│    - Router dispatches role → runner → adapter                   │
└──────────────────────────────────────────────────────────────────┘
           ↓ (emit)
    event_log (.jsonl)
           ↓ (append)
┌──────────────────────────────────────────────────────────────────┐
│ ArtifactStore                                                     │
│  ai-artifacts/{task_id}/{name}.json|.md                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

- **Read:** `docs/architecture.md` for system design
- **Learn:** `docs/ai_delivery_approach_v_1.md` for delivery model
- **Configure:** Edit `system/orchestrator/orchestrator.yaml.local` with your GitHub repo
- **Run:** `breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local`
- **Monitor:** Watch TUI; inspect `ai-artifacts/` and `.breqy/orchestrator/events.jsonl`


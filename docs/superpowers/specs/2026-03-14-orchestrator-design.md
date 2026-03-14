# Orchestrator Design Spec
**Date:** 2026-03-14
**Status:** Approved

---

## 1. Purpose

Build a Phase 2 delivery workflow orchestrator as described in `docs/ai_delivery_approach_v_1.md`. The orchestrator manages the full task lifecycle from intake to merge — loading tasks, routing to the right agent role and AI provider, managing state transitions, gating on CI, and capturing lessons. It replaces `scripts/claude_guardian.py` (which becomes obsolete) and adds a Textual TUI for live human visibility.

---

## 2. Location

```
system/orchestrator/        # all orchestrator source
system/orchestrator/orchestrator.yaml   # config and routing rules
ai-artifacts/               # repo root — task artifacts
.breqy/orchestrator/        # runtime state and event log
```

`scripts/claude_guardian.py` and `scripts/agents.yaml` are retired once the orchestrator is running. Session management (rate limit detection, wait-for-window, resume) moves into the runner layer.

---

## 3. Module layout

```
system/
  orchestrator/
    __init__.py
    main.py                     # CLI entry: parse args, wire deps, start loop + TUI
    config.py                   # Config + routing rule models (Pydantic)
    state_machine.py            # TaskState enum (16 states), transition table, guards
    router.py                   # (task_type, component, role) → runner + adapter
    task_loader.py              # GitHub Issues primary, local YAML fallback
    artifact_store.py           # Read/write ai-artifacts/<task_id>/*
    branch_manager.py           # Git: create branch, status, stale check, rebase
    github_adapter.py           # gh CLI: issue labels/state, PR create/view
    ci_adapter.py               # gh run list/view — poll CI, gate on green
    session_manager.py          # Rate limit detection, ccusage polling, resume logic
    event_log.py                # Append-only JSONL event writer
    runners/
      __init__.py
      base.py                   # AgentRunner ABC: run(prompt, context) → RunResult
      claude_runner.py          # claude -p ... --output-format stream-json
      codex_runner.py
      gemini_runner.py
      copilot_runner.py
    agent_adapters/
      __init__.py
      base.py                   # AgentAdapter ABC: build_prompt(), parse_output()
      planner.py
      doer.py
      checker.py
      tester.py
      qa_automation.py
      lessons.py
    prompts/
      planner.md
      doer.md
      checker.md
      tester.md
      qa_automation.md
      lessons.md
    schemas/
      task_envelope.py          # Pydantic: TaskEnvelope
      artifacts.py              # Pydantic: ReviewArtifact, TestArtifact, LessonsArtifact
      run_result.py             # Pydantic: RunResult
      events.py                 # Pydantic: OrchestratorEvent
    tui/
      __init__.py
      app.py                    # Textual App: root layout, mounts panels
      panels/
        task_panel.py           # Active task metadata
        pipeline_panel.py       # 16-state progress view
        agent_panel.py          # Live agent output stream
        log_panel.py            # Recent events from JSONL log

ai-artifacts/
  <task_id>/
    task-envelope.yaml
    branch-info.yaml
    test-cases.yaml
    doer-report.json
    checker-report.yaml
    deterministic-test-report.json
    qa-automation-report.json
    merge-readiness.yaml
    lessons.yaml
    lessons-learned.md
    instruction-update-proposal.md

.breqy/
  orchestrator/
    events.jsonl                # append-only orchestrator event log
    orchestrator.yaml           # runtime state (tasks, last run)
```

---

## 4. State machine

16 states with explicit transition guards and rework loop limits.

```
NEW
  → READY_FOR_SHAPING          (automatic on task load)

READY_FOR_SHAPING
  → READY_FOR_BRANCH_PREP      (planner artifact written + parsed)

READY_FOR_BRANCH_PREP
  → READY_FOR_TEST_CASE_DESIGN (guard: branch exists in git)

READY_FOR_TEST_CASE_DESIGN
  → READY_FOR_DOER             (tester writes test-cases.yaml)

READY_FOR_DOER
  → DOER_IN_PROGRESS           (doer agent spawned)

DOER_IN_PROGRESS
  → READY_FOR_CHECKER          (guard: doer-report.json exists)

READY_FOR_CHECKER
  → READY_FOR_TESTER           (guard: checker-report.yaml status == pass)
  → CHECK_FAILED               (guard: checker-report.yaml status == fail)

CHECK_FAILED
  → READY_FOR_DOER             (guard: rework_count < max_rework_loops)
  → BLOCKED                    (guard: rework_count >= max_rework_loops)

READY_FOR_TESTER
  → READY_FOR_QA_AUTOMATION    (guard: deterministic-test-report.json status == pass)
  → TEST_FAILED                (guard: status == fail)

TEST_FAILED
  → READY_FOR_DOER             (guard: rework_count < max_rework_loops)
  → BLOCKED                    (guard: rework_count >= max_rework_loops)

READY_FOR_QA_AUTOMATION
  → READY_FOR_MERGE_REVIEW     (guard: qa-automation-report.json status == pass)
  → TEST_FAILED                (guard: status == fail)

READY_FOR_MERGE_REVIEW
  → READY_FOR_LESSONS          (guard: CI green via ci_adapter)

READY_FOR_LESSONS
  → READY_FOR_HUMAN_REVIEW     (guard: lessons.yaml written)

READY_FOR_HUMAN_REVIEW
  → DONE                       (guard: PR merged in GitHub)

any → BLOCKED                  (manual block or max rework exceeded)
```

**State persistence:** dual-written to GitHub Issue label (one label per state, swapped on transition) and `.breqy/orchestrator/orchestrator.yaml` runtime file. Issue label is the human-visible source of truth; local file is the orchestrator's restart source of truth.

**Rework counter:** tracked per task in the local runtime file. Configurable `max_rework_loops` (default: 3). Exceeding it moves the task to BLOCKED and emits an escalation event.

**Every transition** emits an `OrchestratorEvent` to `.breqy/orchestrator/events.jsonl`.

---

## 5. Role routing and agent adapters

### Routing config (`system/orchestrator/orchestrator.yaml`)

```yaml
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
      checker:       codex
      tester:        gemini
      qa_automation: gemini
      lessons:       claude
  bug:
    low_risk:
      doer:          copilot
      checker:       codex
      tester:        gemini
      qa_automation: none
      lessons:       claude
  refactor:
    service:
      doer:          claude
      checker:       codex
      tester:        gemini
      qa_automation: none
      lessons:       claude

agent_defaults:
  planner:       claude
  doer:          claude
  checker:       codex
  tester:        gemini
  qa_automation: claude
  lessons:       claude
```

### AgentAdapter (`agent_adapters/base.py`)

Owns **what to say** — prompt composition per role:

```python
class AgentAdapter(ABC):
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        # Loads prompts/<role>.md + appends task envelope + relevant prior artifacts
        ...

    def parse_output(self, result: RunResult) -> dict:
        # Extracts: artifact paths written, status (pass/fail), session_id
        ...
```

Role-specific context injection:
- **Checker**: appends `doer-report.json` + git diff
- **Doer (rework)**: appends `checker-report.yaml` findings
- **Lessons**: appends all task artifacts as full audit trail

### AgentRunner (`runners/base.py`)

Owns **how to say it** — CLI invocation per agent type:

```python
class AgentRunner(ABC):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        # Spawns subprocess, streams output, detects rate limits,
        # waits for window if needed (via session_manager), resumes if session_id exists
        ...
```

`RunResult` carries: `status` (completed/rate_limited/failed), `output`, `session_id`, `artifacts_written`, `exit_code`.

Session continuity: rate limit detection from stderr, `ccusage` polling (Claude), resume via `--resume <session_id>`. `session_manager.py` provides shared wait-for-window logic used by all runners.

---

## 6. Task loading

**Primary — GitHub Issues:**

```
gh issue list --label orchestrator:managed --json number,title,body,labels
→ parse TaskEnvelope from YAML block in issue body
→ emit TaskLoaded event per new task
```

Issues must carry the label `orchestrator:managed` and have a valid `TaskEnvelope` YAML block in the body.

**Fallback — local YAML:**

```
glob system/orchestrator/tasks/*.yaml
→ parse TaskEnvelope from file
→ used when offline, for testing, or manual injection
```

If a task exists in both sources, the GitHub Issue takes priority.

---

## 7. Branch management

`branch_manager.py` wraps `git` subprocess calls:

```
create_branch(task_id, task_type, slug) → feat/BRQ-144-session-resume-flow
branch_exists(name)                     → bool
is_stale(name, max_age_days)            → bool  (triggers StaleWarning event)
current_branch()                        → str
push(name)                              → void
```

Naming convention (from `agents/core.instructions.md`): `feat/<task-id>-<slug>`, `fix/`, `refactor/` etc. Slug is kebab-cased title, truncated to 40 chars.

---

## 8. GitHub and CI adapters

### GitHub adapter (`github_adapter.py`)

State labels:
```
set_task_state(issue_number, new_state)
  → gh issue edit <n> --remove-label "state:*" --add-label "state:<new_state>"
get_task_state(issue_number) → TaskState
```

PR management:
```
create_pr(branch, title, body) → pr_url
get_pr_status(pr_url)          → PrStatus
pr_is_merged(pr_url)           → bool   (gates READY_FOR_HUMAN_REVIEW → DONE)
```

### CI adapter (`ci_adapter.py`)

```
get_latest_run(branch)          → CiRun (id, status, conclusion)
wait_for_green(branch, timeout) → bool
  → polls every 60s up to timeout
  → emits CiPolling events to JSONL log
```

`conclusion: success` → gate passes. `failure`/`cancelled` → emit CiFailed event, task stays in READY_FOR_MERGE_REVIEW, human intervention required.

---

## 9. Event log

Every significant orchestrator action appends one JSON line to `.breqy/orchestrator/events.jsonl`.

```python
class OrchestratorEvent(BaseModel):
    event_id: str           # ULID
    timestamp: str          # ISO8601
    task_id: str
    event_type: str         # state_transition | agent_spawn | agent_complete |
                            # artifact_written | ci_poll | ci_result |
                            # rate_limit | rework_loop | blocked | error
    from_state: str | None
    to_state: str | None
    role: str | None        # planner | doer | checker | tester | qa | lessons
    agent_type: str | None  # claude | codex | gemini | copilot
    artifact_paths: list[str]
    notes: str
```

The event log is the audit trail consumed by the TUI log panel, future agents (as lessons context), and external tooling.

---

## 10. Textual TUI

Launched alongside the orchestrator loop in `main.py`. The loop runs in a background thread; the TUI owns the main thread. They communicate via a thread-safe queue — the loop pushes `OrchestratorEvent` objects; the TUI consumes them to update panels reactively.

### Layout

```
┌─────────────────────────────┬──────────────────────────────┐
│  PIPELINE                   │  ACTIVE TASK                 │
│                             │                              │
│  ○ NEW                      │  ID:     BRQ-144             │
│  ○ READY_FOR_SHAPING        │  Type:   feature / backend   │
│  ● DOER_IN_PROGRESS  ←here  │  State:  DOER_IN_PROGRESS    │
│  ○ READY_FOR_CHECKER        │  Role:   doer                │
│  ○ ...                      │  Agent:  claude              │
│  ○ DONE                     │  Rework: 0 / 3               │
│                             │  Branch: feat/BRQ-144-...    │
│                             │  PR:     —                   │
├─────────────────────────────┴──────────────────────────────┤
│  AGENT OUTPUT                                              │
│  [doer/claude] Implementing session resume flow...         │
│  [doer/claude] [tool] Edit                                 │
│  [doer/claude] Writing tests first...                      │
├────────────────────────────────────────────────────────────┤
│  EVENT LOG                                                 │
│  14:03:21  state_transition  READY_FOR_DOER → DOER_IN_...  │
│  14:03:19  agent_spawn       doer / claude  BRQ-144        │
│  14:01:55  state_transition  BRANCH_PREP → TEST_CASE_...   │
└────────────────────────────────────────────────────────────┘
```

### Panels

- **`pipeline_panel.py`** — all 16 states listed vertically; current state highlighted; completed states marked; BLOCKED/FAILED states in red
- **`task_panel.py`** — active task metadata: ID, type, component, state, role, agent, rework count, branch, PR URL
- **`agent_panel.py`** — live tail of runner subprocess stdout (last 50 lines); tool calls, text, and rate limit events in real time
- **`log_panel.py`** — scrollable recent events from JSONL log, newest at bottom, colour-coded by event type

### Startup sequence (`main.py`)

```
1. Parse args, load orchestrator.yaml
2. Initialise all components (inject deps)
3. Start orchestrator loop in background thread
4. Launch Textual App (blocks main thread until user quits)
5. On quit: signal loop to stop, wait for clean shutdown
```

---

## 11. Configuration (`system/orchestrator/orchestrator.yaml`)

```yaml
github:
  repo: owner/repo
  managed_label: orchestrator:managed
  ci_timeout_minutes: 30
  ci_poll_interval_seconds: 60

orchestrator:
  poll_interval_seconds: 30
  max_rework_loops: 3
  artifact_base: ai-artifacts
  event_log: .breqy/orchestrator/events.jsonl
  runtime_state: .breqy/orchestrator/orchestrator.yaml
  task_fallback_dir: system/orchestrator/tasks

routing_rules:
  # ... (see section 5)
```

All secrets (GitHub token, API keys) via environment variables or `SecretProvider` — never in this file. A `.env.sample` is provided.

---

## 12. Key interfaces

```python
# runners/base.py
class AgentRunner(ABC):
    def run(self, prompt: str, context: RunContext) -> RunResult: ...

# agent_adapters/base.py
class AgentAdapter(ABC):
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str: ...
    def parse_output(self, result: RunResult) -> dict: ...

# state_machine.py
class StateMachine:
    def can_transition(self, task: Task, to: TaskState) -> bool: ...
    def transition(self, task: Task, to: TaskState) -> Task: ...

# task_loader.py
class TaskLoader(ABC):
    def load_pending(self) -> list[TaskEnvelope]: ...

# artifact_store.py
class ArtifactStore:
    def write(self, task_id: str, name: str, content: dict | str) -> Path: ...
    def read(self, task_id: str, name: str) -> dict | str | None: ...
    def exists(self, task_id: str, name: str) -> bool: ...
```

---

## 13. What this replaces

| Old | New |
|---|---|
| `scripts/claude_guardian.py` | `runners/<agent>_runner.py` + `session_manager.py` |
| `scripts/agents.yaml` | `system/orchestrator/orchestrator.yaml` |
| Manual state tracking | `state_machine.py` + GitHub Issue labels |
| Ad hoc artifact locations | `artifact_store.py` + `ai-artifacts/<task_id>/` |

---

## 14. Out of scope for this implementation

- Phase 3: LLM-assisted orchestration (PRD decomposition, failure summarisation)
- Phase 4: continuous daemon / backlog watching
- Multi-task parallelism (one active task at a time in v1)
- Web dashboard
- Historical trend analysis

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
    state_machine.py            # StateMachine ABC + concrete impl, TaskState enum (17 states)
    router.py                   # (task_type, component, role) → runner + adapter
    task_loader.py              # CompositeTaskLoader: GitHub Issues primary, YAML fallback
    github_task_loader.py       # GitHubTaskLoader: gh CLI, issue body parsing
    local_task_loader.py        # LocalYamlTaskLoader: glob system/orchestrator/tasks/*.yaml
    artifact_store.py           # Read/write ai-artifacts/<task_id>/*
    branch_manager.py           # Git: create/rebase branch, stale check, merge target
    github_adapter.py           # gh CLI: issue labels/state, PR create/view
    ci_adapter.py               # gh run list/view — poll CI, gate on green
    session_manager.py          # Rate limit detection, ccusage polling, resume logic (Claude)
    event_log.py                # Append-only JSONL event writer
    runners/
      __init__.py               # exports: AgentRunner, RunResult, RunContext
      base.py                   # AgentRunner ABC: run(prompt, context) → RunResult
      claude_runner.py          # claude -p ... --output-format stream-json --resume <sid>
      codex_runner.py           # codex ... (session continuity: TBD per CLI support)
      gemini_runner.py          # gemini ... (session continuity: TBD per CLI support)
      copilot_runner.py         # gh copilot ... (session continuity: TBD per CLI support)
    agent_adapters/
      __init__.py               # exports: AgentAdapter, TaskContext, ParsedOutput
      base.py                   # AgentAdapter ABC: build_prompt(), parse_output()
      planner.py
      doer.py
      checker.py
      tester.py
      qa_automation.py
      lessons.py
    prompts/                    # markdown files, no __init__.py needed
      planner.md
      doer.md
      checker.md
      tester.md
      qa_automation.md
      lessons.md
    schemas/
      __init__.py               # exports: TaskEnvelope, RunResult, OrchestratorEvent, ParsedOutput, *Artifact
      task_envelope.py          # Pydantic: TaskEnvelope (from delivery approach section 6.3)
      artifacts.py              # Pydantic: ReviewArtifact, TestArtifact, LessonsArtifact, ParsedOutput
      run_result.py             # Pydantic: RunResult, RunContext
      events.py                 # Pydantic: OrchestratorEvent
    tui/
      __init__.py
      app.py                    # Textual App: root layout, mounts panels
      panels/
        task_panel.py           # Active task metadata
        pipeline_panel.py       # 17-state progress view
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
    instruction-update-proposal.md  # produced by lessons adapter when applicable

.breqy/
  orchestrator/
    events.jsonl                # append-only orchestrator event log
    runtime-state.yaml          # runtime state (active tasks, last run, rework counts)
```

---

## 4. State machine

17 states. The `StateMachine` is an ABC; the concrete implementation is injected via DI:

```python
class StateMachine(ABC):
    def can_transition(self, task: Task, to: TaskState) -> bool: ...
    def transition(self, task: Task, to: TaskState) -> Task: ...
```

### States and transitions

```
NEW
  → READY_FOR_SHAPING          (guard: all dependencies in DONE state)

READY_FOR_SHAPING
  → READY_FOR_BRANCH_PREP      (guard: planner artifact written + parsed cleanly)

READY_FOR_BRANCH_PREP
  → READY_FOR_TEST_CASE_DESIGN (guard: branch exists in git)

READY_FOR_TEST_CASE_DESIGN
  → READY_FOR_DOER             (guard: tester writes test-cases.yaml)

READY_FOR_DOER
  → DOER_IN_PROGRESS           (doer agent spawned)

DOER_IN_PROGRESS
  → READY_FOR_CHECKER          (guard: doer-report.json exists)
  → RETRY_PENDING              (guard: runner raised transient error, retry_count < max_retries)
  → BLOCKED                    (guard: runner raised transient error, retry_count >= max_retries)

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
  → QA_FAILED                  (guard: status == fail)

QA_FAILED
  → READY_FOR_DOER             (guard: failure_source == broken_implementation,
                                        rework_count < max_rework_loops)
  → READY_FOR_QA_AUTOMATION    (guard: failure_source == broken_automation,
                                        rework_count < max_rework_loops)
  → BLOCKED                    (guard: rework_count >= max_rework_loops
                                        OR failure_source == ambiguous_criteria)

READY_FOR_MERGE_REVIEW
  → READY_FOR_LESSONS          (guard: CI green AND merge-readiness.yaml written)

READY_FOR_LESSONS
  → READY_FOR_HUMAN_REVIEW     (guard: lessons.yaml written)

READY_FOR_HUMAN_REVIEW
  → DONE                       (guard: PR merged in GitHub)

RETRY_PENDING
  → DOER_IN_PROGRESS           (guard: retry_count < max_retries, after backoff)
  → BLOCKED                    (guard: retry_count >= max_retries)

any → BLOCKED                  (manual block or limits exceeded)
```

### Dependency guard

`NEW → READY_FOR_SHAPING` requires all task `dependencies` (from `TaskEnvelope.dependencies`) to be in state `DONE`. The orchestrator checks this on each poll cycle. Tasks with unsatisfied dependencies stay in `NEW` and emit a `dependency_wait` event to the JSONL log.

### QA failure routing

`QA_FAILED` carries a `failure_source` field:
- `broken_implementation` → rework routes back to `READY_FOR_DOER`
- `broken_automation` → rework routes back to `READY_FOR_QA_AUTOMATION` (automation script is the problem)
- `ambiguous_criteria` → task moves to `BLOCKED`, human escalation required

The `qa_automation` adapter is responsible for setting `failure_source` in `qa-automation-report.json`.

### Merge-readiness review

`READY_FOR_MERGE_REVIEW → READY_FOR_LESSONS` requires two gates:
1. **CI green** — `ci_adapter.wait_for_green(branch)` returns `True`
2. **Merge-readiness artifact** — `merge-readiness.yaml` written by a deterministic orchestrator check (not an LLM), verifying: all required artifacts exist, branch is current (not stale), merge target is `dev`, CI conclusion is `success`

`merge-readiness.yaml` required fields:
```yaml
task_id: BRQ-144
checked_at: 2026-03-14T14:03:21Z
artifacts_present: [task-envelope, doer-report, checker-report, test-report, qa-report, lessons]
branch: feat/BRQ-144-session-resume-flow
merge_target: dev
ci_conclusion: success
branch_is_current: true
verdict: pass   # or fail
notes: ""
```

This is a deterministic orchestrator operation; no agent role is assigned for it.

### Error recovery

Transient runner/adapter errors (subprocess crash, network timeout, file write failure) move the task to `RETRY_PENDING` rather than immediately to `BLOCKED`. The orchestrator retries after a configurable backoff. `max_retries` is separate from `max_rework_loops` — retries are for infrastructure failures, rework loops are for agent-quality failures. If all retries are exhausted, the task moves to `BLOCKED` and emits an `error` event with full context.

### State persistence

Dual-written:
- **GitHub Issue label** — `state:<STATE_NAME>` label, swapped on each transition. Human-visible source of truth.
- **`.breqy/orchestrator/runtime-state.yaml`** — orchestrator's restart source of truth. Stores current state, rework counts, retry counts, session IDs, last artifact paths per task.

Note: the config file is `system/orchestrator/orchestrator.yaml`; the runtime state file is `.breqy/orchestrator/runtime-state.yaml` — two distinct files with distinct purposes.

Every transition emits an `OrchestratorEvent` to `.breqy/orchestrator/events.jsonl`.

---

## 5. Role routing and agent adapters

### Routing config (`system/orchestrator/orchestrator.yaml`)

Missing role keys mean the stage is **skipped** and the corresponding states are bypassed. The table below documents which states are bypassed per skipped role:

| Skipped role | States bypassed |
|---|---|
| `planner` | `READY_FOR_SHAPING` → jumps to `READY_FOR_BRANCH_PREP` |
| `qa_automation` | `READY_FOR_QA_AUTOMATION` → jumps to `READY_FOR_MERGE_REVIEW` |

All other roles are mandatory and cannot be omitted.

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
      # planner omitted — READY_FOR_SHAPING bypassed
      doer:          copilot
      checker:       codex
      tester:        gemini
      # qa_automation omitted — READY_FOR_QA_AUTOMATION bypassed
      lessons:       claude
  refactor:
    service:
      doer:          claude
      checker:       codex
      tester:        gemini
      # qa_automation omitted — READY_FOR_QA_AUTOMATION bypassed
      lessons:       claude

agent_defaults:
  planner:       claude
  doer:          claude
  checker:       codex
  tester:        gemini
  qa_automation: claude
  lessons:       claude
```

`agent_defaults` apply when a task type/component combination is not in `routing_rules`.

### AgentAdapter (`agent_adapters/base.py`)

Owns **what to say** — prompt composition per role:

```python
class ParsedOutput(BaseModel):
    status: Literal["pass", "fail"]
    artifact_paths: list[str]
    failure_source: str | None = None   # for qa_automation adapter
    session_id: str | None = None
    notes: str = ""

class AgentAdapter(ABC):
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        # Loads prompts/<role>.md + appends task envelope + relevant prior artifacts
        ...

    def parse_output(self, result: RunResult) -> ParsedOutput:
        # Extracts structured data from agent output
        ...
```

Role-specific context injection:
- **Checker**: appends `doer-report.json` + git diff
- **Doer (rework)**: appends `checker-report.yaml` findings
- **QA Automation (rework)**: appends `qa-automation-report.json` with `failure_source`
- **Lessons**: appends all task artifacts as full audit trail; writes `lessons.yaml`, `lessons-learned.md`, and `instruction-update-proposal.md` when applicable

**Lessons storage decision:** all lessons artifacts (`lessons.yaml`, `lessons-learned.md`, `instruction-update-proposal.md`) live under `ai-artifacts/<task_id>/` only. Both `ai_delivery_approach_v_1.md` section 14.2 and `project.instructions.md` section 15 permit this location. The `.breqy/lessons/` alternative is not used — keeping all task artifacts in one place simplifies the artifact store and makes the audit trail self-contained per task.

### AgentRunner (`runners/base.py`)

Owns **how to say it** — CLI invocation per agent type:

```python
class AgentRunner(ABC):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        # Spawns subprocess, streams output, detects rate limits,
        # waits for window if needed, resumes if session_id exists
        ...
```

`RunResult` carries: `status` (completed/rate_limited/failed), `output`, `session_id`, `artifacts_written`, `exit_code`.

### Runner invocation patterns

| Runner | CLI invocation | Session continuity |
|---|---|---|
| `claude_runner.py` | `claude -p <prompt> --output-format stream-json --permission-mode acceptEdits` | `--resume <session_id>` via `ccusage` polling in `session_manager.py` |
| `codex_runner.py` | `codex <prompt>` | TBD — depends on Codex CLI session support |
| `gemini_runner.py` | `gemini <prompt>` | TBD — depends on Gemini CLI session support |
| `copilot_runner.py` | `gh copilot suggest <prompt>` | TBD — depends on Copilot CLI session support |

`session_manager.py` provides Claude-specific session continuity (rate limit detection via stderr keywords, `ccusage blocks` polling, wait-for-window). Non-Claude runners use a simpler retry-on-failure strategy until their CLIs expose session resume mechanisms.

---

## 6. Task loading

`task_loader.py` contains `CompositeTaskLoader` which wraps both concrete loaders:

```python
class TaskLoader(ABC):
    def load_pending(self) -> list[TaskEnvelope]: ...

class GitHubTaskLoader(TaskLoader):      # github_task_loader.py
    ...

class LocalYamlTaskLoader(TaskLoader):   # local_task_loader.py
    ...

class CompositeTaskLoader(TaskLoader):   # task_loader.py
    # GitHub Issues primary; falls back to local YAML for tasks not found on GitHub
    # If same task_id exists in both sources, GitHub Issue takes priority
    ...
```

**GitHub Issues:**
```
gh issue list --label orchestrator:managed --json number,title,body,labels
→ parse TaskEnvelope from YAML block in issue body
→ emit TaskLoaded event per new task
```

Issues must carry the label `orchestrator:managed` and have a valid `TaskEnvelope` YAML block in the body matching the schema in `docs/ai_delivery_approach_v_1.md` section 6.3.

**Local YAML fallback:**
```
glob system/orchestrator/tasks/*.yaml
→ parse TaskEnvelope from file
→ used when offline, for testing, or manual injection
```

---

## 7. Branch management

`branch_manager.py` wraps `git` subprocess calls. Branch naming uses the project's authoritative convention from `agents/core.instructions.md`:

| Task type | Branch prefix | Example |
|---|---|---|
| feature | `feat/` | `feat/BRQ-144-session-resume-flow` |
| bug | `fix/` | `fix/BRQ-201-reconnect-duplication` |
| refactor | `refactor/` | `refactor/BRQ-233-session-service-cleanup` |
| hotfix | `hotfix/` | `hotfix/BRQ-299-critical-auth-bypass` |

Note: `core.instructions.md` takes precedence over the longer `feature/` prefix used in `ai_delivery_approach_v_1.md` examples. All agents and the orchestrator use `feat/` for consistency with the in-repo authoritative source.

Slug: kebab-cased task title, max 40 chars, lowercased, non-alphanumeric chars replaced with `-`.

```python
class BranchManager:
    def create_branch(self, task_id: str, task_type: str, slug: str) -> str: ...
    def branch_exists(self, name: str) -> bool: ...
    def is_stale(self, name: str, max_age_days: int) -> bool: ...
    def rebase(self, name: str, onto: str) -> None: ...
    def merge_target(self, task_type: str) -> str:
        # features/bugs/refactors → "dev"
        # hotfixes → "main"
        ...
    def current_branch(self) -> str: ...
    def push(self, name: str) -> None: ...
```

When `is_stale()` returns `True`, the orchestrator emits a `StaleWarning` event and invokes `rebase(name, merge_target(task_type))` before the next agent run. If rebase fails, the task moves to `BLOCKED`.

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
  → polls every ci_poll_interval_seconds (default 60)
  → emits CiPolling events to JSONL log
```

`conclusion: success` → gate passes. `failure`/`cancelled` → emit `CiFailed` event, task stays in `READY_FOR_MERGE_REVIEW`, human intervention required.

---

## 9. Event log

Every significant orchestrator action appends one JSON line to `.breqy/orchestrator/events.jsonl`.

```python
class OrchestratorEvent(BaseModel):
    event_id: str                    # ULID
    timestamp: str                   # ISO8601
    task_id: str
    event_type: str                  # state_transition | agent_spawn | agent_complete |
                                     # artifact_written | ci_poll | ci_result |
                                     # rate_limit | rework_loop | blocked | error |
                                     # dependency_wait | stale_warning | retry_pending
    from_state: str | None = None
    to_state: str | None = None
    role: str | None = None          # planner | doer | checker | tester | qa | lessons
    agent_type: str | None = None    # claude | codex | gemini | copilot
    artifact_paths: list[str] = []
    notes: str = ""
```

The event log is the audit trail consumed by the TUI log panel, future agents (as lessons context), and external tooling.

---

## 10. Textual TUI

Launched alongside the orchestrator loop in `main.py`. The loop runs in a background thread; the TUI owns the main thread. They communicate via a thread-safe `queue.Queue` — the loop pushes `OrchestratorEvent` objects; the TUI's async watcher consumes them to update panels reactively.

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

- **`pipeline_panel.py`** — all 17 states listed vertically; current state highlighted; completed states marked; BLOCKED/FAILED/QA_FAILED states in red
- **`task_panel.py`** — active task metadata: ID, type, component, state, role, agent, rework count, branch, PR URL
- **`agent_panel.py`** — live tail of runner subprocess stdout (last 50 lines); tool calls, text, and rate limit events in real time
- **`log_panel.py`** — scrollable recent events from JSONL log, newest at bottom, colour-coded by event type

### Startup sequence (`main.py`)

```
1. Parse args, load orchestrator.yaml
2. Initialise all components (inject deps via DI)
3. Start orchestrator loop in background thread
4. Register SIGINT/SIGTERM handlers (signal.signal on main thread)
5. Launch Textual App (blocks main thread until user quits or signal received)
6. On shutdown signal:
   a. Set stop event on orchestrator loop
   b. Wait up to 30s for current atomic runner step to finish
   c. Force-terminate runner subprocess if still alive after timeout
   d. Flush event log
   e. Write runtime-state.yaml
   f. Exit
```

This shutdown contract ensures in-flight `ai-artifacts/` writes are not corrupted — the orchestrator waits for the current subprocess's atomic step before terminating, consistent with the "Stop and steer" control primitive.

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
  max_retries: 3                          # transient infrastructure failures
  retry_backoff_seconds: 60
  artifact_base: ai-artifacts
  event_log: .breqy/orchestrator/events.jsonl
  runtime_state: .breqy/orchestrator/runtime-state.yaml
  task_fallback_dir: system/orchestrator/tasks
  branch_stale_days: 3

routing_rules:
  # ... (see section 5)
```

### Environment variables (`.env.sample` at repo root)

```bash
# GitHub
GITHUB_TOKEN=                   # required: gh CLI auth token

# AI provider API keys (only set keys for providers used in routing_rules)
ANTHROPIC_API_KEY=              # Claude runners
OPENAI_API_KEY=                 # Codex runners
GOOGLE_API_KEY=                 # Gemini runners
GITHUB_COPILOT_TOKEN=           # Copilot runners
```

All secrets via environment variables only — never in `orchestrator.yaml` or any committed file.

---

## 12. Key interfaces

```python
# state_machine.py
class StateMachine(ABC):
    def can_transition(self, task: Task, to: TaskState) -> bool: ...
    def transition(self, task: Task, to: TaskState) -> Task: ...

# runners/base.py
class AgentRunner(ABC):
    def run(self, prompt: str, context: RunContext) -> RunResult: ...

# agent_adapters/base.py
class AgentAdapter(ABC):
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str: ...
    def parse_output(self, result: RunResult) -> ParsedOutput: ...

# task_loader.py / github_task_loader.py / local_task_loader.py
class TaskLoader(ABC):
    def load_pending(self) -> list[TaskEnvelope]: ...

# artifact_store.py
class ArtifactStore:
    def write(self, task_id: str, name: str, content: BaseModel | str) -> Path: ...
    def read(self, task_id: str, name: str, model: type[T]) -> T | None: ...
    def read_text(self, task_id: str, name: str) -> str | None: ...  # for .md files
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
- Glob/wildcard pattern matching in routing rules

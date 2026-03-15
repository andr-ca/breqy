# Breqy Orchestrator

Automated AI delivery workflow that drives tasks from intake to merge using multiple AI providers, with a live Textual TUI.

---

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- `gh` CLI authenticated to GitHub
- At least one AI CLI available: `claude`, `codex`, `gemini`, `gh copilot`, or `qwen`

---

## Quick start

All commands run from the **repo root** (the directory containing `pyproject.toml`).

```bash
# Install
uv sync

# Copy and edit the config — keep it at the repo root
cp system/orchestrator/orchestrator.yaml orchestrator.yaml
# Edit: set github.repo to your repo (owner/name)

# Run with TUI (from repo root)
uv run breqy-orchestrator --config orchestrator.yaml

# Run without TUI (headless)
uv run breqy-orchestrator --config orchestrator.yaml --no-tui
```

> The `--config` path is relative to your **current working directory** when you run the command.

---

## How tasks get picked up

The orchestrator loads tasks from two sources (GitHub wins on duplicate `task_id`):

1. **GitHub Issues** — issues labelled `orchestrator:managed` (or the label set in `github.managed_label`) that contain a YAML block in the body:

   ````
   ```yaml
   task_id: BRQ-42
   title: Add session resume
   task_type: feature
   component: backend
   acceptance_criteria:
     - Session resumes without data loss
   ```
   ````

2. **Local YAML files** — `*.yaml` files in `orchestrator.task_fallback_dir` (default: `system/orchestrator/tasks/`):

   ```yaml
   # system/orchestrator/tasks/BRQ-42.yaml
   task_id: BRQ-42
   title: Add session resume
   task_type: feature
   component: backend
   acceptance_criteria:
     - Session resumes without data loss
   dependencies: []   # optional: list of task_ids that must be DONE first
   ```

### Supported `task_type` values

`feature` · `bug` · `refactor` · `hotfix`

---

## Task lifecycle (18 states)

```
NEW
 └─ dep gate passes ──► READY_FOR_SHAPING
                           └─► READY_FOR_BRANCH_PREP
                                 └─► READY_FOR_TEST_CASE_DESIGN
                                       └─► READY_FOR_DOER
                                             └─► DOER_IN_PROGRESS
                                                   └─► READY_FOR_CHECKER
                                                   │     └─ fail ─► CHECK_FAILED ──► rework or BLOCKED
                                                   └─► READY_FOR_TESTER
                                                         └─ fail ─► TEST_FAILED ──► rework or BLOCKED
                                                         └─► READY_FOR_QA_AUTOMATION
                                                               └─ fail ─► QA_FAILED ──► BLOCKED
                                                               └─► READY_FOR_MERGE_REVIEW
                                                                     └─► READY_FOR_LESSONS
                                                                           └─► READY_FOR_HUMAN_REVIEW
                                                                                 └─► DONE
BLOCKED        — operator intervention needed
RETRY_PENDING  — rate-limited, waiting for window
```

---

## Configuration

`orchestrator.yaml` (full reference):

```yaml
github:
  repo: owner/repo              # required
  managed_label: orchestrator:managed
  ci_timeout_minutes: 30
  ci_poll_interval_seconds: 60

orchestrator:
  poll_interval_seconds: 30
  max_rework_loops: 3           # CHECK_FAILED / TEST_FAILED / QA_FAILED before BLOCKED
  max_retries: 3                # rate-limit retries before BLOCKED
  retry_backoff_seconds: 60
  artifact_base: ai-artifacts   # dir where run artifacts are written
  event_log: .breqy/orchestrator/events.jsonl
  runtime_state: .breqy/orchestrator/runtime-state.yaml
  task_fallback_dir: system/orchestrator/tasks
  branch_stale_days: 3

# Default AI runner per role (claude | codex | gemini | copilot | qwen)
agent_defaults:
  planner:       claude
  doer:          claude
  checker:       codex
  tester:        gemini
  qa_automation: claude
  lessons:       claude

# Override per (task_type, component, role) — more specific wins
routing_rules:
  feature:
    backend:
      doer:    claude
      checker: codex
  bug:
    low_risk:
      doer:    copilot
```

### Required environment variables

Copy `.env.sample` to `.env` and fill in the tokens your runners need:

```
ANTHROPIC_API_KEY=       # claude runner
OPENAI_API_KEY=          # codex runner
GOOGLE_API_KEY=          # gemini runner
GITHUB_COPILOT_TOKEN=    # copilot runner
DASHSCOPE_API_KEY=       # qwen runner
GITHUB_TOKEN=            # gh CLI (issues, PRs, CI)
```

---

## Artifacts

Each task produces artifacts under `ai-artifacts/<task_id>/`:

| File | Written by |
|---|---|
| `doer-instructions.yaml` | Planner |
| `doer-report.json` | Doer |
| `checker-report.yaml` | Checker |
| `deterministic-test-report.json` | Tester |
| `qa-automation-report.json` | QA Automation |
| `lessons.yaml` + `lessons-learned.md` | Lessons |
| `merge-readiness.json` | Orchestrator (merge gate) |

---

## Customising agent prompts

Each role has a Markdown prompt template in `system/orchestrator/prompts/`:

```
prompts/
  planner.md
  doer.md
  checker.md
  tester.md
  qa_automation.md
  lessons.md
```

Edit these freely — the orchestrator reloads them at each invocation.

---

## TUI layout

```
┌──────────────────────┬───────────────────────────────────┐
│  Pipeline            │  Task info                        │
│  ○ NEW               │  ID:     BRQ-42                   │
│  ● READY_FOR_DOER    │  Title:  Add session resume       │
│  ✓ DOER_IN_PROGRESS  │  State:  READY_FOR_CHECKER        │
│  ...                 │  Rework: 0 / 3                    │
├──────────────────────┴───────────────────────────────────┤
│  Agent output   [doer/claude] Running TDD cycle...       │
├──────────────────────────────────────────────────────────┤
│  Events   14:23:01  state_transition  BRQ-42             │
└──────────────────────────────────────────────────────────┘
```

Press `ctrl+c` for graceful shutdown (waits for current step to finish).

---

## Running tests

```bash
uv run pytest tests/unit/orchestrator/        # unit tests
uv run pytest tests/integration/orchestrator/ # integration tests
uv run pytest tests/ --cov=system/orchestrator --cov-report=term-missing
```

---

## Project layout

```
system/orchestrator/
  main.py              # CLI entry point
  orchestrator.py      # OrchestratorLoop (core state driver)
  config.py            # OrchestratorConfig, load_config()
  state_machine.py     # 18-state TaskState, ConcreteStateMachine
  router.py            # (task_type, component, role) → runner + adapter
  task_loader.py       # TaskLoader ABC, CompositeTaskLoader
  local_task_loader.py # loads tasks/*.yaml
  github_task_loader.py# loads GitHub Issues with yaml blocks
  artifact_store.py    # typed read/write under ai-artifacts/
  event_log.py         # append-only JSONL event writer
  branch_manager.py    # git branch lifecycle
  github_adapter.py    # gh issue/PR management
  ci_adapter.py        # gh run polling, CI green gate
  session_manager.py   # Claude session continuity, rate-limit detection
  runners/             # AgentRunner ABC + ClaudeRunner, CodexRunner, etc.
  agent_adapters/      # AgentAdapter ABC + 6 role adapters
  prompts/             # Markdown prompt templates (one per role)
  tui/                 # Textual TUI (App, PipelinePanel, TaskPanel, etc.)
  orchestrator.yaml    # Default config template
```

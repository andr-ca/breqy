# Quick Start: Running the Breqy Orchestrator

## 60-Second Setup

### 1. Install

```bash
cd /home/andrey/projects/breqy
uv sync
```

### 2. Configure

```bash
# Copy config template
cp system/orchestrator/orchestrator.yaml system/orchestrator/orchestrator.yaml.local

# Edit with your GitHub repo
nano system/orchestrator/orchestrator.yaml.local
```

Change this line:
```yaml
github:
  repo: owner/repo          # ← Change to your GitHub repo (e.g., myuser/myrepo)
```

### 3. Set Environment Variables

Create `.env` in project root:
```bash
GITHUB_TOKEN=ghp_your_token_here
ANTHROPIC_API_KEY=sk_your_key_here
OPENAI_API_KEY=sk_your_key_here
GOOGLE_API_KEY=your_key_here
DASHSCOPE_API_KEY=your_key_here
```

### 4. Start the App

**With TUI (recommended):**
```bash
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local
```

**Without TUI (CLI only):**
```bash
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local --no-tui
```

---

## What You'll See

### TUI Dashboard

```
╔══════════════════════════════════════════════════════════════════╗
║ Breqy Orchestrator                                               ║
╠══════════════════════════════════════════════════════════════════╣
║ Pipeline                        │ Task Info                      ║
║ ○ NEW                          │ ID:     BRQ-1                  ║
║ ● READY_FOR_SHAPING            │ Title:  Login endpoint         ║
║ ○ SHAPING_IN_PROGRESS          │ Type:   feature / backend      ║
║ ○ READY_FOR_PLANNING_REVIEW    │ State:  READY_FOR_SHAPING     ║
║ ○ PLANNING_REVIEW_PASSED       │ Role:   planner                ║
║ ○ READY_FOR_DOER               │ Agent:  claude                 ║
║ ○ DOER_IN_PROGRESS             │ Rework: 0 / 3                  ║
║ ...                            │ Branch: feat/BRQ-1-login      ║
║                                │ PR:     https://github...      ║
╠══════════════════════════════════════════════════════════════════╣
║ Agent Logs                                                       ║
║ [planner/claude] Starting task planning...                       ║
║ [doer/claude] Implementing feature...                            ║
╠══════════════════════════════════════════════════════════════════╣
║ Event Log                                                        ║
║ 14:30:22  state_transition      BRQ-1  Task envelope created   ║
║ 14:30:45  agent_spawn           BRQ-1  Starting planner        ║
║ 14:31:12  agent_complete        BRQ-1  Planner done            ║
║ 14:31:13  state_transition      BRQ-1  Ready for doer          ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Create Your First Task

### Option A: Local YAML File

Create `system/orchestrator/tasks/BRQ-1.yaml`:

```yaml
task_id: BRQ-1
title: Add login endpoint
description: Implement POST /auth/login with JWT token response
task_type: feature
component: backend
dependencies: []
acceptance_criteria:
  - POST /auth/login accepts username and password
  - Returns JWT token on success
  - Returns 401 on invalid credentials
test_hints:
  - Test with valid username/password
  - Test with invalid credentials
  - Test with missing fields
priority: high
labels:
  - orchestrator:managed
github_issue_number: 1
```

The orchestrator will pick it up on next poll (default: 30 seconds).

### Option B: GitHub Issue

1. Create issue in your repo
2. Add label: `orchestrator:managed`
3. Add YAML block to issue body:

```markdown
## Description

Implement login endpoint with JWT token response.

```yaml
task_id: BRQ-1
title: Add login endpoint
task_type: feature
component: backend
acceptance_criteria:
  - POST /auth/login accepts username and password
  - Returns JWT token on success
test_hints:
  - Test with valid and invalid credentials
```

The orchestrator will fetch and process it.

---

## Shutdown

Press `Ctrl+C` — the orchestrator will:
1. Stop the loop
2. Wait for current agent to finish (up to 30 seconds)
3. Kill any runaway processes
4. Flush event log
5. Exit cleanly

---

## Monitor Progress

### View Event Log

```bash
# Watch in real-time
tail -f .breqy/orchestrator/events.jsonl | jq '.'

# Pretty-print last 10 events
tail .breqy/orchestrator/events.jsonl | jq '.' | head -50
```

### View Task Artifacts

```bash
# Shaped task (created by planner)
cat ai-artifacts/BRQ-1/shaped-task.json | jq '.'

# Doer implementation report
cat ai-artifacts/BRQ-1/doer-report.json | jq '.'

# Code review findings
cat ai-artifacts/BRQ-1/review.json | jq '.'

# Test results
cat ai-artifacts/BRQ-1/test-results.json | jq '.'

# QA results
cat ai-artifacts/BRQ-1/qa-results.json | jq '.'

# Lessons learned
cat ai-artifacts/BRQ-1/lessons.json | jq '.'
```

### Check Task Status

```bash
# List all artifacts for a task
ls -la ai-artifacts/BRQ-1/

# Count total events
wc -l .breqy/orchestrator/events.jsonl

# Filter events by task
grep "BRQ-1" .breqy/orchestrator/events.jsonl | jq '.'

# Filter by event type
grep "state_transition" .breqy/orchestrator/events.jsonl | jq '.'
```

---

## Troubleshooting

### "ImportError: No module named 'orchestrator'"

```bash
uv sync
export PYTHONPATH=/home/andrey/projects/breqy:$PYTHONPATH
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local
```

### "Config not found: system/orchestrator/orchestrator.yaml.local"

```bash
# Ensure config exists
cp system/orchestrator/orchestrator.yaml system/orchestrator/orchestrator.yaml.local

# Verify it's readable
cat system/orchestrator/orchestrator.yaml.local | head -5
```

### "FileNotFoundError: owner/repo"

Edit `orchestrator.yaml.local` and change:
```yaml
github:
  repo: myusername/myrepo    # Use your actual repo
```

### "401 Unauthorized" (GitHub API)

Check `GITHUB_TOKEN` in `.env`:
```bash
# Generate new token at https://github.com/settings/tokens
# Needs: repo (full control), read:org

cat .env | grep GITHUB_TOKEN
# If missing, add it and run: source .env
```

### "rate_limited — waiting for window"

This is normal. The orchestrator detects rate limits and waits:
1. Check `ccusage blocks --json` to see remaining quota
2. Wait for window to open automatically
3. Task resumes with `--resume session_id`

Watch the log:
```bash
tail -f .breqy/orchestrator/events.jsonl | grep rate_limit
```

### "Task stuck in NEW"

Check dependencies:
```bash
# Find dependency_wait events
grep "dependency_wait" .breqy/orchestrator/events.jsonl | jq '.'

# Check if dependencies are DONE
grep "BRQ-100\|BRQ-101" .breqy/orchestrator/events.jsonl | jq '.to_state'
```

### "No tasks found"

1. Check local YAML tasks:
   ```bash
   ls -la system/orchestrator/tasks/
   ```

2. Check GitHub issues:
   ```bash
   # With label: orchestrator:managed
   gh issue list --repo owner/repo --label orchestrator:managed
   ```

3. If using GitHub, ensure `GITHUB_TOKEN` is set and has `repo` scope

---

## CLI Options

```bash
breqy-orchestrator --help
```

Output:
```
usage: breqy-orchestrator [-h] [--config CONFIG] [--no-tui]

Breqy Orchestrator

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG       Path to orchestrator.yaml (default: system/orchestrator/orchestrator.yaml)
  --no-tui              Run without TUI (CLI only)
```

Examples:
```bash
# Default config, with TUI
breqy-orchestrator

# Custom config, with TUI
breqy-orchestrator --config /path/to/orchestrator.yaml

# Custom config, no TUI (logs to stdout)
breqy-orchestrator --config /path/to/orchestrator.yaml --no-tui

# Run in background
nohup breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local --no-tui > orchestrator.log 2>&1 &
```

---

## State Machine Overview

```
NEW (waiting for dependencies to complete)
  ↓
READY_FOR_SHAPING (planner will analyze task)
  ↓
DOER_IN_PROGRESS (implementation happening)
  ↓
CODE_REVIEW_IN_PROGRESS (checker reviewing code)
  ↓ [found issues? → READY_FOR_REWORK (rework loop, max 3)]
  ↓
TESTING_IN_PROGRESS (tester running tests)
  ↓ [tests fail? → READY_FOR_RETRY (retry loop, max 3)]
  ↓
QA_IN_PROGRESS (QA automation running)
  ↓ [QA fails? → READY_FOR_QA_RETRY (retry loop)]
  ↓
READY_FOR_MERGE (merge-readiness check passed)
  ↓
MERGED (GitHub PR merged)
  ↓
LESSONS_TRIGGERED (lessons agent captures learnings)
  ↓
DONE (task complete!)

[BLOCKED] (terminal: exhausted retries/rework)
[FAILED] (terminal: unrecoverable error)
```

---

## Performance & Optimization

### Poll Interval

Faster = more responsive, higher CPU:
```yaml
orchestrator:
  poll_interval_seconds: 5    # Default: 30
```

### Rework & Retry Limits

Max attempts before BLOCKED:
```yaml
orchestrator:
  max_rework_loops: 3         # Code review rework
  max_retries: 3              # Test retry
```

### Concurrency

Currently **sequential** (one task at a time). Future: parallel agents.

---

## Full Documentation

For detailed information on:
- **Architecture:** See `docs/architecture.md`
- **Orchestrator API:** See `docs/orchestrator.md`
- **Configuration:** See `docs/orchestrator.md` → Configuration
- **Task Lifecycle:** See `docs/orchestrator.md` → Task Lifecycle

---

## Example Session

```bash
# 1. Start
breqy-orchestrator --config system/orchestrator/orchestrator.yaml.local

# 2. In another terminal, watch events
tail -f .breqy/orchestrator/events.jsonl | jq '.event_type, .to_state, .task_id'

# 3. View artifacts as they're created
watch -n 1 'ls -la ai-artifacts/BRQ-1/'

# 4. On completion, inspect results
cat ai-artifacts/BRQ-1/lessons.json | jq '.lessons'

# 5. Shutdown
# Press Ctrl+C in orchestrator terminal
```

---

Happy orchestrating! 🚀

# Task Hot-Reload Design

**Date:** 2026-03-17
**Status:** Approved

## Problem

Tasks are loaded once at orchestrator startup. Adding a new local YAML file or GitHub Issue requires a restart to be picked up. Removing a task (deleting a file or closing/unlabelling an issue) while the orchestrator is running has no effect.

## Goal

- New tasks appear automatically on the next poll tick (no restart required)
- Removed tasks are cancelled, their git branch deleted, and a cancellation event emitted
- If the removed task has a running process, that process is killed first

## Approach

Poll `CompositeTaskLoader` on every loop iteration (Option A — inline polling). Uses the existing 30-second tick cadence. No new threads, no new dependencies.

## Design

### 1. `OrchestratorLoop` changes

**Constructor:** gains `loader: TaskLoader | None = None`.

**`run()` signature change:** removes the `tasks: list[tuple[Task, TaskEnvelope]]` parameter. On the first iteration the loop calls `loader.load_pending()` to build `all_tasks`. On every subsequent tick it calls `load_pending()` again and diffs:

- `task_id` present in loader result but absent from `all_tasks` → insert `(Task(task_id=…, state=NEW), env)`
- `task_id` present in `all_tasks` but absent from loader result, and state not in `{DONE, BLOCKED}` → call `_cancel_task(task, env)` then remove from `all_tasks`

Tasks already `DONE` or `BLOCKED` are never cancelled even if they disappear from the source.

**New field:** `_current_task_id: str | None = None` — tracks which task owns `_current_process`, so cancellation can kill only the right process.

### 2. Cancel/rollback — `_cancel_task(task, env)`

Executed in order:

1. **Kill process** — if `_current_task_id == task.task_id` and process is alive, call `force_kill_current()`
2. **Delete branch** — if `task.branch` is set, call `BranchManager.delete_branch(task.branch)`
3. **Emit event** — `task_cancelled` event with `task_id` and last known state, written to event log and TUI queue
4. **Remove** — caller removes task from `all_tasks`

Tasks with `task.branch is None` (e.g. still in `NEW` / `READY_FOR_SHAPING`) skip step 2.

### 3. `BranchManager.delete_branch(name)`

```
git branch -D <name>          # local, check=False (no-op if missing)
git push origin --delete <name>  # remote, check=False (silent if never pushed)
```

Both failures swallowed — a missing branch during cancellation must not crash the orchestrator.

### 4. `main.py` changes

- `_build_loop` returns `(loop, event_queue, config, loader)` — the `CompositeTaskLoader` is passed into `OrchestratorLoop` at construction
- The task-loading block that ran before `loop_thread.start()` is removed
- `OrchestratorApp` (TUI) receives an empty initial task list — it already updates via `event_queue` and needs no bootstrap list

## Event schema addition

`OrchestratorEvent.event_type` gains the value `"task_cancelled"`. The `notes` field carries the last known state.

## Testing

- Unit: `OrchestratorLoop` diff logic (new task detected, removed task triggers cancel)
- Unit: `BranchManager.delete_branch` (local delete, remote delete, missing branch no-ops)
- Unit: `_cancel_task` — process kill when `_current_task_id` matches; branch deletion called when `task.branch` is set; event emitted
- Integration: loader returns fewer tasks on second call → cancellation fires

## Out of scope

- Updating an existing task envelope mid-flight (title/criteria changes)
- Immediate detection of local file changes (inotify/watchdog) — 30s cadence is sufficient

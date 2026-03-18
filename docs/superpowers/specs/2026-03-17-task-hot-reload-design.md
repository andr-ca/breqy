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

**`run()` signature change:** removes the `tasks: list[tuple[Task, TaskEnvelope]]` parameter — it now takes no arguments. `all_tasks: dict[str, tuple[Task, TaskEnvelope]] = {}` is initialised once **before** the `while` loop. The diff runs at the **top of every iteration**:

- `task_id` present in loader result but absent from `all_tasks` → insert `(Task(task_id=…, state=NEW), env)`
- `task_id` present in `all_tasks` but absent from loader result, and state not in `{DONE, BLOCKED}` → call `_cancel_task(task, env)` then remove from `all_tasks`

Tasks already `DONE` or `BLOCKED` are never cancelled even if they disappear from the source. `RETRY_PENDING` is treated as cancellable — a task disappearing from the source while waiting to retry is cancelled.

**New field:** `_current_task_id: str | None = None` — tracks which task owns `_current_process`. Set to `task.task_id` when the runner layer assigns `_current_process`; cleared to `None` when the process completes or is killed.

**`main.py` changes:**
- Loader construction (`GitHubTaskLoader`, `LocalYamlTaskLoader`, `CompositeTaskLoader`) stays in `_run_orchestrator` (not moved into `_build_loop`)
- The loader is passed directly into `OrchestratorLoop(…, loader=composite)` at construction in `_run_orchestrator`
- `_build_loop` return type is unchanged — it remains `(OrchestratorLoop, queue.Queue, OrchestratorConfig)`; the loader assembly that currently follows `_build_loop` is removed from `_run_orchestrator` and replaced with the single `OrchestratorLoop` constructor call with `loader=`
- Thread invocation changes to `threading.Thread(target=loop.run, args=(), …)` — no args passed

### 2. Cancel/rollback — `_cancel_task(task, env)`

Executed in order:

1. **Kill process** — if `_current_task_id == task.task_id` and process is alive, call `force_kill_current()`, then set `_current_process = None` and `_current_task_id = None`
2. **Delete branch** — if `task.branch` is set, call `BranchManager.delete_branch(task.branch)`. If the branch is currently checked out, local deletion will fail silently (`check=False`) — this is a known gap; the branch will be left in place but no crash occurs. Remote deletion is still attempted.
3. **Emit event** — `task_cancelled` event with `task_id`, `from_state=task.state.value`, written to event log and TUI queue
4. **Remove** — caller removes task from `all_tasks`

Tasks with `task.branch is None` (e.g. still in `NEW` / `READY_FOR_SHAPING`) skip step 2.

**Re-added tasks:** if a task is cancelled and later re-added under the same `task_id`, it is treated as a fresh `NEW` task. If the remote branch deletion from the prior cancellation did not propagate, `BranchManager.create_branch` may conflict. This edge case is accepted for now.

### 3. `BranchManager.delete_branch(name)` — new method

```python
def delete_branch(self, name: str) -> None:
    self._run("git", "branch", "-D", name, check=False)
    self._run("git", "push", "origin", "--delete", name, check=False)
```

Both calls use tokenised `args` consistent with `BranchManager._run`'s use of `subprocess.run(args, ...)`. Both failures are swallowed — a missing branch during cancellation must not crash the orchestrator.

### 4. `main.py` changes

- Loader construction stays in `_run_orchestrator`; the assembled `CompositeTaskLoader` is passed to `OrchestratorLoop(…, loader=composite)` at construction
- The separate task-loading block and `tasks` variable that previously existed between `_build_loop` and `loop_thread.start()` are removed
- Thread invocation: `threading.Thread(target=loop.run, args=(), …)`
- `OrchestratorApp` (TUI) receives an empty initial task list — it already updates via `event_queue`

### 5. TUI changes

**`TaskPanel`:** dynamically loaded tasks will not appear in `_tasks` until a state-transition event arrives that triggers `handle_event`. Because `OrchestratorEvent` carries only `task_id` (not a full `TaskEnvelope`), the `_tasks` dict cannot be populated from new-task events alone — task detail display for dynamically loaded tasks will be absent until the task transitions state and `handle_event` is called with a known `task_id`. The `task_cancelled` handler removes the entry from `_tasks` if present. This limitation is accepted for Slice 1.

**`PipelinePanel`:** the current implementation tracks a single active pipeline (not per-task rows). The `task_cancelled` handler must check: if the cancelled `task_id` is the currently-displayed task, reset `_current` and `_completed` to empty state. If it is not the currently-displayed task, no action needed.

### 6. Event schema

`OrchestratorEvent.event_type` gains the value `"task_cancelled"`. Use `from_state=task.state.value` to record the last known state — consistent with how `state_transition` events use `from_state`/`to_state`. The inline comment on the `event_type` field in `schemas/events.py` must be updated to include `"task_cancelled"`.

## Testing

- Unit: `OrchestratorLoop` diff logic — new task detected and inserted as NEW; removed non-terminal task triggers `_cancel_task`; DONE/BLOCKED tasks are not cancelled when removed
- Unit: `BranchManager.delete_branch` — local delete called; remote delete called; neither raises on missing branch
- Unit: `_cancel_task` — process and `_current_process`/`_current_task_id` cleared when `_current_task_id` matches; branch deletion called when `task.branch` is set; branch deletion skipped when `task.branch is None`; `task_cancelled` event emitted with `from_state`
- Unit: `PipelinePanel` handles `task_cancelled` for current task (resets state) and non-current task (no-op)
- Integration: loader returns fewer tasks on second call → cancellation fires and task is removed from `all_tasks`

## Out of scope

- Updating an existing task envelope mid-flight (title/criteria changes)
- Immediate detection of local file changes (inotify/watchdog) — 30s cadence is sufficient
- Recovering from checked-out branch deletion failure
- Populating `TaskPanel._tasks` from new-task events (requires envelope data in event schema)

# Task Hot-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll both task sources (local YAML + GitHub Issues) on every orchestrator loop tick so new tasks are picked up and removed tasks are cancelled without restarting.

**Architecture:** `OrchestratorLoop` gains a `loader: TaskLoader | None` and a new `_sync_tasks(all_tasks)` method that diffs loader results against the live task dict on each tick. `run()` loses its `tasks` parameter — it owns `all_tasks` internally. Removal triggers `_cancel_task`: kill process, delete git branch, emit `task_cancelled` event.

**Tech Stack:** Python 3.12, pytest, unittest.mock — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-17-task-hot-reload-design.md`

---

## File Map

| Action | File |
|--------|------|
| Modify (comment only) | `system/orchestrator/schemas/events.py:30-32` |
| Modify (add method) | `system/orchestrator/branch_manager.py` |
| Modify (add fields + methods, change `run`) | `system/orchestrator/orchestrator.py` |
| Modify (wire loader, change thread call) | `system/orchestrator/main.py` |
| Modify (handle `task_cancelled`) | `system/orchestrator/tui/panels/pipeline_panel.py` |
| Modify (handle `task_cancelled`) | `system/orchestrator/tui/panels/task_panel.py` |
| Modify (add tests) | `tests/unit/orchestrator/test_branch_manager.py` |
| Modify (add tests) | `tests/unit/orchestrator/test_orchestrator_loop.py` |
| Modify (add tests) | `tests/unit/orchestrator/test_tui_app.py` |
| Modify (add integration tests) | `tests/integration/orchestrator/test_orchestrator_loop.py` |

---

## Task 1: Update `events.py` comment

**Files:**
- Modify: `system/orchestrator/schemas/events.py:30-32`

No behaviour change — adds `task_cancelled` to the `event_type` inline comment so the schema stays self-documenting.

- [ ] **Step 1: Edit the comment**

In `system/orchestrator/schemas/events.py`, change line 31–32 from:
```python
    event_type: str  # state_transition | agent_spawn | agent_complete | artifact_written |
    # ci_poll | ci_result | rate_limit | rework_loop | blocked | error |
    # dependency_wait | stale_warning | retry_pending
```
to:
```python
    event_type: str  # state_transition | agent_spawn | agent_complete | artifact_written |
    # ci_poll | ci_result | rate_limit | rework_loop | blocked | error |
    # dependency_wait | stale_warning | retry_pending | task_cancelled
```

- [ ] **Step 2: Run existing tests to confirm nothing broken**

```bash
python3 -m pytest tests/unit/orchestrator/ -q
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add system/orchestrator/schemas/events.py
git commit -m "docs(events): add task_cancelled to event_type comment"
```

---

## Task 2: `BranchManager.delete_branch`

**Files:**
- Modify: `system/orchestrator/branch_manager.py`
- Test: `tests/unit/orchestrator/test_branch_manager.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/orchestrator/test_branch_manager.py`:

```python
def test_delete_branch_issues_local_and_remote_delete(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        bm.delete_branch("feat/BRQ-1-test")
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["git", "branch", "-D", "feat/BRQ-1-test"] in calls
    assert ["git", "push", "origin", "--delete", "feat/BRQ-1-test"] in calls


def test_delete_branch_does_not_raise_when_branch_missing(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="branch not found")
        bm.delete_branch("feat/BRQ-1-test")  # must not raise


def test_delete_branch_does_not_raise_when_remote_missing(bm):
    results = [
        MagicMock(returncode=0, stdout="", stderr=""),   # local delete ok
        MagicMock(returncode=1, stdout="", stderr="remote ref not found"),  # remote fails
    ]
    with patch("subprocess.run", side_effect=results):
        bm.delete_branch("feat/BRQ-1-test")  # must not raise
```

- [ ] **Step 2: Confirm tests fail**

```bash
python3 -m pytest tests/unit/orchestrator/test_branch_manager.py::test_delete_branch_issues_local_and_remote_delete -v
```
Expected: `AttributeError: 'BranchManager' object has no attribute 'delete_branch'`

- [ ] **Step 3: Implement `delete_branch`**

Add to `system/orchestrator/branch_manager.py` after the `push` method:

```python
def delete_branch(self, name: str) -> None:
    """Delete branch locally and on remote. Silently ignores missing branches."""
    self._run("git", "branch", "-D", name, check=False)
    self._run("git", "push", "origin", "--delete", name, check=False)
```

- [ ] **Step 4: Run new tests**

```bash
python3 -m pytest tests/unit/orchestrator/test_branch_manager.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/branch_manager.py tests/unit/orchestrator/test_branch_manager.py
git commit -m "feat(branch): add delete_branch for task cancellation rollback"
```

---

## Task 3: `OrchestratorLoop._cancel_task`

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

Adds two new constructor fields (`_loader`, `_branch_manager`, `_current_task_id`) and the `_cancel_task` method. Does **not** change `run()` yet — that's Task 4.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
def test_cancel_task_emits_task_cancelled_event(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._cancel_task(task, env)
    event = loop._queue.get_nowait()
    assert event.event_type == "task_cancelled"
    assert event.task_id == "BRQ-1"
    assert event.from_state == "DOER_IN_PROGRESS"


def test_cancel_task_deletes_branch_when_set(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS, branch="feat/BRQ-1-test")
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_bm = MagicMock()
    loop._branch_manager = mock_bm
    loop._cancel_task(task, env)
    mock_bm.delete_branch.assert_called_once_with("feat/BRQ-1-test")


def test_cancel_task_skips_branch_deletion_when_no_branch(loop):
    task = Task(task_id="BRQ-1", state=TaskState.NEW)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_bm = MagicMock()
    loop._branch_manager = mock_bm
    loop._cancel_task(task, env)
    mock_bm.delete_branch.assert_not_called()


def test_cancel_task_kills_process_when_task_id_matches(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running
    loop._current_process = mock_proc
    loop._current_task_id = "BRQ-1"
    loop._cancel_task(task, env)
    mock_proc.terminate.assert_called_once()
    assert loop._current_process is None
    assert loop._current_task_id is None


def test_cancel_task_does_not_kill_process_when_task_id_differs(loop):
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    loop._current_process = mock_proc
    loop._current_task_id = "BRQ-2"
    loop._cancel_task(task, env)
    mock_proc.terminate.assert_not_called()
    assert loop._current_task_id == "BRQ-2"
```

- [ ] **Step 2: Confirm tests fail**

```bash
python3 -m pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_cancel_task_emits_task_cancelled_event -v
```
Expected: `AttributeError: 'OrchestratorLoop' object has no attribute '_cancel_task'`

- [ ] **Step 3: Add constructor fields and `_cancel_task` to `orchestrator.py`**

In `OrchestratorLoop.__init__`, add two new parameters and initialise three new fields:

```python
def __init__(
    self,
    config: OrchestratorConfig,
    state_machine: ConcreteStateMachine,
    artifact_store: ArtifactStore,
    event_log: EventLog,
    event_queue: queue.Queue,
    credential_store: CredentialStore | None = None,
    loader: "TaskLoader | None" = None,
    branch_manager: "BranchManager | None" = None,
) -> None:
    ...
    self._loader = loader
    self._branch_manager = branch_manager
    self._current_task_id: str | None = None
```

Add the import at the top of the file:
```python
from system.orchestrator.task_loader import TaskLoader
from system.orchestrator.branch_manager import BranchManager
```

Add the `_cancel_task` method to `OrchestratorLoop`:

```python
def _cancel_task(self, task: Task, env: TaskEnvelope) -> None:
    """Kill running process, delete git branch, emit task_cancelled event."""
    if self._current_task_id == task.task_id:
        self.force_kill_current()
        self._current_process = None
        self._current_task_id = None
    if task.branch and self._branch_manager is not None:
        self._branch_manager.delete_branch(task.branch)
    self._emit(OrchestratorEvent(
        task_id=task.task_id,
        event_type="task_cancelled",
        from_state=task.state.value,
    ))
```

- [ ] **Step 4: Run new tests**

```bash
python3 -m pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: all pass (including pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add _cancel_task with process kill, branch delete, event emit"
```

---

## Task 4: `OrchestratorLoop._sync_tasks` + change `run()`

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/orchestrator/test_orchestrator_loop.py`:

```python
def test_sync_tasks_adds_new_task(loop):
    all_tasks = {}
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = [env]
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert all_tasks["BRQ-1"][0].state == TaskState.NEW


def test_sync_tasks_does_not_overwrite_existing_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = [env]
    loop._sync_tasks(all_tasks)
    assert all_tasks["BRQ-1"][0].state == TaskState.READY_FOR_SHAPING


def test_sync_tasks_cancels_removed_non_terminal_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []  # task gone
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" not in all_tasks
    event = loop._queue.get_nowait()
    assert event.event_type == "task_cancelled"


def test_sync_tasks_does_not_cancel_done_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.DONE)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert loop._queue.empty()


def test_sync_tasks_does_not_cancel_blocked_task(loop):
    env = TaskEnvelope(task_id="BRQ-1", title="t", task_type="feature", component="backend")
    task = Task(task_id="BRQ-1", state=TaskState.BLOCKED)
    all_tasks = {"BRQ-1": (task, env)}
    loop._loader = MagicMock()
    loop._loader.load_pending.return_value = []
    loop._sync_tasks(all_tasks)
    assert "BRQ-1" in all_tasks
    assert loop._queue.empty()


def test_sync_tasks_no_op_when_loader_is_none(loop):
    all_tasks = {}
    loop._loader = None
    loop._sync_tasks(all_tasks)  # must not raise
    assert all_tasks == {}


def test_run_calls_sync_tasks_each_tick(loop):
    call_count = [0]
    def fake_load():
        call_count[0] += 1
        loop._stop_event.set()  # stop after first call
        return []
    loop._loader = MagicMock()
    loop._loader.load_pending.side_effect = fake_load
    loop.run()
    assert call_count[0] == 1
```

- [ ] **Step 2: Confirm tests fail**

```bash
python3 -m pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_sync_tasks_adds_new_task -v
```
Expected: `AttributeError: 'OrchestratorLoop' object has no attribute '_sync_tasks'`

- [ ] **Step 3: Add `_sync_tasks` and update `run()`**

Add `_sync_tasks` to `OrchestratorLoop`:

```python
def _sync_tasks(self, all_tasks: dict[str, tuple[Task, TaskEnvelope]]) -> None:
    """Diff loader results against all_tasks: insert new, cancel removed."""
    if self._loader is None:
        return
    fresh = {env.task_id: env for env in self._loader.load_pending()}
    for task_id, env in fresh.items():
        if task_id not in all_tasks:
            all_tasks[task_id] = (Task(task_id=task_id, state=TaskState.NEW), env)
    to_cancel = [
        (task, env)
        for task_id, (task, env) in list(all_tasks.items())
        if task_id not in fresh and task.state not in (TaskState.DONE, TaskState.BLOCKED)
    ]
    for task, env in to_cancel:
        self._cancel_task(task, env)
        del all_tasks[task.task_id]
```

Replace `run()` — remove the `tasks` parameter, initialise `all_tasks` before the loop, call `_sync_tasks` at the top of every iteration:

```python
def run(self) -> None:
    """Main loop — polls for tasks and processes them until stop() is called."""
    all_tasks: dict[str, tuple[Task, TaskEnvelope]] = {}
    while not self._stop_event.is_set():
        self._sync_tasks(all_tasks)
        for task_id, (task, env) in list(all_tasks.items()):
            task = self._tick(task, env, all_tasks)
            all_tasks[task_id] = (task, env)
        time.sleep(self._config.orchestrator.poll_interval_seconds)
```

- [ ] **Step 4: Run all orchestrator unit tests**

```bash
python3 -m pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
git commit -m "feat(orchestrator): add _sync_tasks hot-reload diff, run() takes no args"
```

---

## Task 5: Update `main.py` + integration tests

**Files:**
- Modify: `system/orchestrator/main.py`
- Modify: `tests/integration/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write new integration tests**

Append to `tests/integration/orchestrator/test_orchestrator_loop.py`:

```python
def _make_loop(tmp_path, tasks_dir):
    cfg = OrchestratorConfig(
        github=GitHubConfig(repo="owner/repo"),
        orchestrator=OrchestratorSettings(poll_interval_seconds=0),
        agent_defaults={"doer": "claude", "checker": "codex", "tester": "gemini", "lessons": "claude"},
    )
    sm = ConcreteStateMachine()
    store = ArtifactStore(base=tmp_path / "artifacts")
    log = EventLog(path=tmp_path / "events.jsonl")
    eq: queue.Queue = queue.Queue()
    loader = LocalYamlTaskLoader(tasks_dir=tasks_dir)
    loop = OrchestratorLoop(
        config=cfg, state_machine=sm,
        artifact_store=store, event_log=log, event_queue=eq,
        loader=loader,
    )
    return loop, eq


def test_hot_reload_picks_up_new_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, _ = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    assert "INT-1" in all_tasks
    assert all_tasks["INT-1"][0].state == TaskState.NEW


def test_hot_reload_cancels_deleted_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, eq = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    assert "INT-1" in all_tasks
    # Remove the task file
    (tasks_dir / "INT-1.yaml").unlink()
    loop._sync_tasks(all_tasks)
    assert "INT-1" not in all_tasks
    event = eq.get_nowait()
    assert event.event_type == "task_cancelled"
    assert event.task_id == "INT-1"
    assert event.from_state == "NEW"


def test_hot_reload_does_not_cancel_done_task(tmp_dirs):
    tmp_path, tasks_dir = tmp_dirs
    loop, eq = _make_loop(tmp_path, tasks_dir)
    all_tasks = {}
    loop._sync_tasks(all_tasks)
    # Advance task to DONE
    task, env = all_tasks["INT-1"]
    all_tasks["INT-1"] = (task.model_copy(update={"state": TaskState.DONE}), env)
    # Remove the file
    (tasks_dir / "INT-1.yaml").unlink()
    loop._sync_tasks(all_tasks)
    # DONE task stays in dict
    assert "INT-1" in all_tasks
    assert eq.empty()
```

- [ ] **Step 2: Run new integration tests (expect pass — `_sync_tasks` exists)**

```bash
python3 -m pytest tests/integration/orchestrator/ -v
```
Expected: all pass (new tests use `_sync_tasks` directly, which was implemented in Task 4).

- [ ] **Step 3: Update `main.py`**

Add `BranchManager` to the **module-level imports** at the top of `main.py` (alongside existing imports):
```python
from system.orchestrator.branch_manager import BranchManager
```

In `_run_orchestrator`, replace the loader assembly + `loop.run(tasks)` block with constructor-injected dependencies. The full updated function body:

```python
def _run_orchestrator(cfg_path: str, no_tui: bool) -> None:
    loop, eq, cfg = _build_loop(Path(cfg_path))

    # Build loaders and wire into loop via constructor-injected fields
    github_loader = GitHubTaskLoader(
        repo=cfg.github.repo, managed_label=cfg.github.managed_label
    )
    local_loader = LocalYamlTaskLoader(tasks_dir=Path(cfg.orchestrator.task_fallback_dir))
    composite = CompositeTaskLoader(github=github_loader, local=local_loader)
    # Reconstruct the loop with loader + branch_manager injected at construction
    from system.orchestrator.artifact_store import ArtifactStore
    from system.orchestrator.event_log import EventLog
    from system.orchestrator.state_machine import ConcreteStateMachine
    cfg2 = cfg  # alias for clarity
    loop = OrchestratorLoop(
        config=cfg2,
        state_machine=loop._sm,
        artifact_store=loop._artifact_store,
        event_log=loop._log,
        event_queue=eq,
        loader=composite,
        branch_manager=BranchManager(repo_root=Path.cwd()),
    )

    # Start orchestrator loop in background thread — run() takes no args
    loop_thread = threading.Thread(
        target=loop.run, args=(), daemon=True, name="orchestrator-loop"
    )
    loop_thread.start()
    ...
    # Pass empty initial tasks to TUI — tasks arrive via event_queue
    app = OrchestratorApp(event_queue=eq, tasks=[])
    ...
```

> Note: The old `envelopes`/`tasks` variable block is removed. `loop_thread` `args` changes from `args=(tasks,)` to `args=()`. `OrchestratorApp` changes from `tasks=tasks` to `tasks=[]`.
>
> The loop is reconstructed after `_build_loop` to inject `loader` and `branch_manager` at construction time (not via post-hoc attribute mutation), keeping the dependency injection contract clean. `_build_loop`'s return type is unchanged.

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/main.py tests/integration/orchestrator/test_orchestrator_loop.py
git commit -m "feat(main): wire hot-reload loader and branch manager into orchestrator loop"
```

---

## Task 6: `PipelinePanel` handles `task_cancelled`

**Files:**
- Modify: `system/orchestrator/tui/panels/pipeline_panel.py`
- Test: `tests/unit/orchestrator/test_tui_app.py`

`PipelinePanel` tracks `_current_task_id` (new) to know whether a cancellation affects the displayed pipeline.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/orchestrator/test_tui_app.py`:

```python
def test_pipeline_panel_tracks_current_task_id_on_state_transition():
    panel = PipelinePanel(id="pipeline")
    event = OrchestratorEvent(
        task_id="BRQ-1", event_type="state_transition",
        from_state="NEW", to_state="READY_FOR_SHAPING",
    )
    panel.handle_event(event)
    assert panel._current_task_id == "BRQ-1"


def test_pipeline_panel_resets_on_cancel_of_current_task():
    panel = PipelinePanel(id="pipeline")
    # Set some state first
    panel.handle_event(OrchestratorEvent(
        task_id="BRQ-1", event_type="state_transition",
        from_state="NEW", to_state="DOER_IN_PROGRESS",
    ))
    assert panel._current == "DOER_IN_PROGRESS"
    # Cancel the same task
    panel.handle_event(OrchestratorEvent(
        task_id="BRQ-1", event_type="task_cancelled",
        from_state="DOER_IN_PROGRESS",
    ))
    assert panel._current is None
    assert panel._completed == set()
    assert panel._current_task_id is None


def test_pipeline_panel_ignores_cancel_of_other_task():
    panel = PipelinePanel(id="pipeline")
    panel.handle_event(OrchestratorEvent(
        task_id="BRQ-1", event_type="state_transition",
        from_state="NEW", to_state="DOER_IN_PROGRESS",
    ))
    # Cancel a *different* task
    panel.handle_event(OrchestratorEvent(
        task_id="BRQ-2", event_type="task_cancelled",
        from_state="NEW",
    ))
    assert panel._current == "DOER_IN_PROGRESS"
    assert panel._current_task_id == "BRQ-1"
```

- [ ] **Step 2: Confirm tests fail**

```bash
python3 -m pytest tests/unit/orchestrator/test_tui_app.py::test_pipeline_panel_tracks_current_task_id_on_state_transition -v
```
Expected: `AssertionError: assert None == "BRQ-1"` (field doesn't exist yet).

- [ ] **Step 3: Update `PipelinePanel`**

```python
class PipelinePanel(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._completed: set[str] = set()
        self._current: str | None = None
        self._current_task_id: str | None = None  # NEW

    def handle_event(self, event: OrchestratorEvent) -> None:
        if event.event_type == "state_transition" and event.to_state:
            self._current_task_id = event.task_id  # NEW
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
        elif event.event_type == "task_cancelled":  # NEW
            if event.task_id == self._current_task_id:
                self._current = None
                self._completed = set()
                self._current_task_id = None
                for state in _STATE_ORDER:
                    try:
                        widget = self.query_one(f"#state-{state.value}", Static)
                        widget.update(f"○ {state.value}")
                    except Exception:
                        pass
```

- [ ] **Step 4: Run panel tests**

```bash
python3 -m pytest tests/unit/orchestrator/test_tui_app.py -v -k "pipeline"
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/tui/panels/pipeline_panel.py tests/unit/orchestrator/test_tui_app.py
git commit -m "feat(tui): pipeline panel resets on task_cancelled for current task"
```

---

## Task 7: `TaskPanel` handles `task_cancelled`

**Files:**
- Modify: `system/orchestrator/tui/panels/task_panel.py`
- Test: `tests/unit/orchestrator/test_tui_app.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/orchestrator/test_tui_app.py`:

```python
def test_task_panel_removes_entry_on_task_cancelled():
    task, env = _make_task_and_env()
    panel = TaskPanel(tasks=[(task, env)], id="task")
    assert "BRQ-1" in panel._tasks
    panel.handle_event(OrchestratorEvent(
        task_id="BRQ-1", event_type="task_cancelled",
        from_state="DOER_IN_PROGRESS",
    ))
    assert "BRQ-1" not in panel._tasks


def test_task_panel_cancel_unknown_task_does_not_raise():
    panel = TaskPanel(tasks=[], id="task")
    panel.handle_event(OrchestratorEvent(
        task_id="UNKNOWN", event_type="task_cancelled",
        from_state="NEW",
    ))  # must not raise
```

- [ ] **Step 2: Confirm tests fail**

```bash
python3 -m pytest tests/unit/orchestrator/test_tui_app.py::test_task_panel_removes_entry_on_task_cancelled -v
```
Expected: `AssertionError: assert "BRQ-1" not in panel._tasks` (entry still present).

- [ ] **Step 3: Update `TaskPanel.handle_event`**

```python
def handle_event(self, event: OrchestratorEvent) -> None:
    if event.event_type == "task_cancelled":  # NEW
        self._tasks.pop(event.task_id, None)
        return
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

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -q
```
Expected: all pass, no warnings beyond the existing `TestArtifact` collection warning.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/tui/panels/task_panel.py tests/unit/orchestrator/test_tui_app.py
git commit -m "feat(tui): task panel removes entry on task_cancelled event"
```

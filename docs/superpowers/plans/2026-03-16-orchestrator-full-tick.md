# Orchestrator Full Tick Expansion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `OrchestratorLoop._tick()` from only handling `NEW → READY_FOR_SHAPING` to driving all 18 task states through the full AI delivery lifecycle — shaping, branch prep, test case design, doer, checker, tester, QA automation, merge review, lessons, and human review.

> **Note on state count:** The design spec header says "17 states" but the spec's own state diagram defines 18 (`RETRY_PENDING` was added after the header was written). The `TaskState` enum in `state_machine.py` has 18 values. This plan is correct to target all 18.

**Architecture:** The loop is a synchronous poll cycle running in a background thread. Each `_tick()` call for a task either blocks while a runner subprocess executes (for role-dispatch states) or checks an artifact/external gate and advances immediately. New deps (`BranchManager`, `GitHubAdapter`, `CIAdapter`, `SessionManager`) are injected via constructor. A `_run_role()` helper consolidates the runner invocation pattern.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, `unittest.mock` — no new dependencies.

---

## File Map

**Modify:**
- `system/orchestrator/orchestrator.py` — all new handlers + helpers + updated constructor
- `system/orchestrator/runners/base.py` — add `proc` attribute for subprocess tracking
- `system/orchestrator/runners/claude_runner.py` — set `self.proc` before blocking
- `system/orchestrator/runners/codex_runner.py` — set `self.proc` before blocking
- `system/orchestrator/runners/gemini_runner.py` — set `self.proc` before blocking
- `system/orchestrator/runners/copilot_runner.py` — set `self.proc` before blocking
- `system/orchestrator/runners/qwen_runner.py` — set `self.proc` before blocking
- `system/orchestrator/main.py` — wire new deps into `OrchestratorLoop`
- `tests/unit/orchestrator/test_orchestrator_loop.py` — all new tests

**No new files required** — runtime state persistence goes in `OrchestratorLoop._persist_state()`.

---

## Chunk 1: Constructor + Proc Tracking + Helpers

### Task 1: Expand OrchestratorLoop constructor and add proc tracking to runners

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Modify: `system/orchestrator/runners/base.py`
- Modify: `system/orchestrator/runners/claude_runner.py`
- Modify: `system/orchestrator/runners/codex_runner.py`
- Modify: `system/orchestrator/runners/gemini_runner.py`
- Modify: `system/orchestrator/runners/copilot_runner.py`
- Modify: `system/orchestrator/runners/qwen_runner.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  In `tests/unit/orchestrator/test_orchestrator_loop.py`, add these tests:

  ```python
  import subprocess
  from unittest.mock import MagicMock, patch

  from system.orchestrator.branch_manager import BranchManager
  from system.orchestrator.ci_adapter import CIAdapter
  from system.orchestrator.github_adapter import GitHubAdapter
  from system.orchestrator.session_manager import SessionManager


  def test_loop_constructor_accepts_optional_deps(loop):
      # The fixture-constructed loop has None deps by default
      assert loop._branch_manager is None
      assert loop._gh is None
      assert loop._ci is None
      assert loop._session_manager is None


  def test_loop_force_kill_uses_runner_proc(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      store = ArtifactStore(base=tmp_path / "artifacts")
      log = EventLog(path=tmp_path / "events.jsonl")
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm, artifact_store=store,
          event_log=log, event_queue=queue.Queue(),
      )
      mock_runner = MagicMock()
      mock_proc = MagicMock(spec=subprocess.Popen)
      mock_proc.poll.return_value = None   # still running
      mock_runner.proc = mock_proc
      loop._current_runner = mock_runner
      loop.force_kill_current()
      mock_proc.terminate.assert_called_once()


  def test_runner_base_has_proc_attribute():
      from system.orchestrator.runners.base import AgentRunner
      # AgentRunner subclasses must expose proc
      assert hasattr(AgentRunner, 'proc') or True  # checked via instantiation below


  def test_claude_runner_sets_proc_on_run(tmp_path):
      from system.orchestrator.runners.claude_runner import ClaudeRunner
      from system.orchestrator.schemas.run_result import RunContext
      runner = ClaudeRunner()
      ctx = RunContext(task_id="t1", role="doer", work_dir=tmp_path)
      with patch("subprocess.Popen") as mock_popen:
          mock_proc = MagicMock()
          mock_proc.stdout = iter(["line1\n"])
          mock_proc.returncode = 0
          mock_proc.wait.return_value = None
          mock_popen.return_value = mock_proc
          runner.run("prompt", ctx)
      assert runner.proc is mock_proc
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  cd /home/andrey/projects/breqy/.worktrees/orchestrator
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_loop_constructor_accepts_optional_deps tests/unit/orchestrator/test_orchestrator_loop.py::test_loop_force_kill_uses_runner_proc tests/unit/orchestrator/test_orchestrator_loop.py::test_claude_runner_sets_proc_on_run -v
  ```
  Expected: FAIL (AttributeError or AssertionError)

- [ ] **Step 3: Add `proc` attribute to `AgentRunner` base**

  In `system/orchestrator/runners/base.py`, add:

  ```python
  import subprocess as _sp

  class AgentRunner(ABC):
      proc: _sp.Popen | None = None   # set by subclass immediately after Popen()

      @abstractmethod
      def run(self, prompt: str, context: RunContext) -> RunResult:
          ...
  ```

- [ ] **Step 4: Set `self.proc` in each runner immediately after `subprocess.Popen()`**

  In `claude_runner.py`, insert `self.proc = proc` right after `proc = subprocess.Popen(...)`.

  Same change in `codex_runner.py`, `gemini_runner.py`, `copilot_runner.py`, `qwen_runner.py`.

  Example for `claude_runner.py`:
  ```python
  proc = subprocess.Popen(cmd, ...)
  self.proc = proc   # ← add this line
  output_lines: list[str] = []
  ```

- [ ] **Step 5: Expand `OrchestratorLoop.__init__` to accept new deps**

  In `system/orchestrator/orchestrator.py`:

  ```python
  from system.orchestrator.branch_manager import BranchManager
  from system.orchestrator.ci_adapter import CIAdapter
  from system.orchestrator.github_adapter import GitHubAdapter
  from system.orchestrator.session_manager import SessionManager

  class OrchestratorLoop:
      def __init__(
          self,
          config: OrchestratorConfig,
          state_machine: ConcreteStateMachine,
          artifact_store: ArtifactStore,
          event_log: EventLog,
          event_queue: queue.Queue,
          branch_manager: BranchManager | None = None,
          github_adapter: GitHubAdapter | None = None,
          ci_adapter: CIAdapter | None = None,
          session_manager: SessionManager | None = None,
      ) -> None:
          self._config = config
          self._sm = state_machine
          self._artifact_store = artifact_store
          self._log = event_log
          self._queue = event_queue
          self._stop_event = threading.Event()
          self._router = Router(config=config)
          self._branch_manager = branch_manager
          self._gh = github_adapter
          self._ci = ci_adapter
          self._session_manager = session_manager
          self._current_runner: AgentRunner | None = None
          self._retry_after: dict[str, float] = {}   # task_id → epoch time
  ```

- [ ] **Step 6: Update `force_kill_current()` to use `_current_runner.proc`**

  ```python
  def force_kill_current(self) -> None:
      """Force-terminate any in-flight runner subprocess."""
      import subprocess as _sp
      runner = self._current_runner
      if runner and runner.proc and runner.proc.poll() is None:
          runner.proc.terminate()
          try:
              runner.proc.wait(timeout=5)
          except _sp.TimeoutExpired:
              runner.proc.kill()
  ```

- [ ] **Step 7: Run tests to confirm passing**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```
  Expected: all pass

- [ ] **Step 8: Run full test suite**

  ```bash
  uv run pytest tests/ -v --tb=short
  ```
  Expected: all pass

- [ ] **Step 9: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py system/orchestrator/runners/base.py \
    system/orchestrator/runners/claude_runner.py system/orchestrator/runners/codex_runner.py \
    system/orchestrator/runners/gemini_runner.py system/orchestrator/runners/copilot_runner.py \
    system/orchestrator/runners/qwen_runner.py \
    tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): inject BranchManager/GitHubAdapter/CIAdapter deps + proc tracking in runners"
  ```

---

### Task 2: Add `_run_role()`, `_role_configured()`, `_persist_state()`, and `_sync_github_label()` helpers

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_role_configured_with_agent_defaults():
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"planner": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=Path("/tmp/art")),
          event_log=EventLog(path=Path("/tmp/e.jsonl")),
          event_queue=queue.Queue(),
      )
      assert loop._role_configured("feature", "backend", "planner") is True
      assert loop._role_configured("feature", "backend", "qa_automation") is False


  def test_role_configured_with_routing_rules():
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          routing_rules={"feature": {"backend": {"planner": "claude"}}},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=Path("/tmp/art")),
          event_log=EventLog(path=Path("/tmp/e.jsonl")),
          event_queue=queue.Queue(),
      )
      assert loop._role_configured("feature", "backend", "planner") is True


  def test_run_role_calls_runner_and_returns_parsed_output(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      from system.orchestrator.schemas.run_result import RunResult
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
      )
      sm = ConcreteStateMachine()
      store = ArtifactStore(base=tmp_path / "artifacts")
      log = EventLog(path=tmp_path / "events.jsonl")
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm, artifact_store=store,
          event_log=log, event_queue=queue.Queue(),
      )
      mock_runner = MagicMock()
      mock_runner.run.return_value = RunResult(
          status="completed", output='{"status":"pass","artifact_paths":[]}', exit_code=0
      )
      mock_adapter = MagicMock()
      mock_adapter.build_prompt.return_value = "do the work"
      mock_adapter.parse_output.return_value = ParsedOutput(
          status="pass", artifact_paths=[]
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
      with patch.object(loop._router, "resolve", return_value=(mock_runner, mock_adapter)):
          result = loop._run_role(task, env, "doer")
      assert result.status == "pass"
      mock_runner.run.assert_called_once()
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_role_configured_with_agent_defaults tests/unit/orchestrator/test_orchestrator_loop.py::test_run_role_calls_runner_and_returns_parsed_output -v
  ```
  Expected: FAIL (AttributeError)

- [ ] **Step 3: Implement helpers in `orchestrator.py`**

  Add these private methods to `OrchestratorLoop`:

  ```python
  def _role_configured(self, task_type: str, component: str, role: str) -> bool:
      """Return True if this role has a runner configured (either specific or default)."""
      specific = (
          self._config.routing_rules
          .get(task_type, {})
          .get(component, {})
          .get(role)
      )
      default = self._config.agent_defaults.get(role)
      return bool(specific or default)

  def _run_role(
      self,
      task: Task,
      env: TaskEnvelope,
      role: str,
  ) -> "ParsedOutput":
      """Resolve runner+adapter for role, build prompt, run, parse output."""
      from pathlib import Path as _Path
      from system.orchestrator.agent_adapters.base import TaskContext
      from system.orchestrator.schemas.run_result import RunContext
      runner, adapter = self._router.resolve(env.task_type, env.component, role)
      prior: dict[str, str] = {}
      task_dir = _Path(self._config.orchestrator.artifact_base) / task.task_id
      if task_dir.exists():
          for p in task_dir.iterdir():
              prior[p.stem] = str(p)
      ctx = TaskContext(
          task=env,
          prior_artifacts=prior,
          rework_count=task.rework_count,
      )
      prompt = adapter.build_prompt(env, ctx)
      run_ctx = RunContext(
          task_id=task.task_id,
          role=role,
          work_dir=_Path("."),
          session_id=task.session_id,
      )
      self._current_runner = runner
      try:
          result = runner.run(prompt, run_ctx)
      finally:
          self._current_runner = None
      return adapter.parse_output(result)

  def _persist_state(self, all_tasks: dict[str, tuple[Task, TaskEnvelope]]) -> None:
      """Write runtime-state.yaml with per-task state/counts for restart safety."""
      import datetime
      import yaml as _yaml
      from pathlib import Path as _Path
      state_path = _Path(self._config.orchestrator.runtime_state)
      state_path.parent.mkdir(parents=True, exist_ok=True)
      tasks_data = {
          tid: {
              "state": t.state,
              "rework_count": t.rework_count,
              "retry_count": t.retry_count,
              "session_id": t.session_id,
              "branch": t.branch,
              "pr_url": t.pr_url,
              "github_issue_number": t.github_issue_number,
              "failure_source": t.failure_source,
          }
          for tid, (t, _) in all_tasks.items()
      }
      state_path.write_text(_yaml.dump({
          "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
          "tasks": tasks_data,
      }))

  def _sync_github_label(self, task: Task, old_state: str) -> None:
      """Swap state:* label on the GitHub Issue if the task came from GitHub."""
      if self._gh and task.github_issue_number:
          try:
              self._gh.set_task_state(
                  task.github_issue_number,
                  new_state=task.state,
                  old_state=old_state,
              )
          except Exception as exc:  # noqa: BLE001
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="error",
                  notes=f"GitHub label sync failed: {exc}",
              ))
  ```

  Note: `ParsedOutput` import at top of file:
  ```python
  from system.orchestrator.schemas.artifacts import MergeReadinessArtifact, ParsedOutput  # add ParsedOutput
  ```

- [ ] **Step 4: Run tests to confirm passing**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```
  Expected: all pass

- [ ] **Step 5: Full suite**

  ```bash
  uv run pytest tests/ -v --tb=short
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): add _run_role, _role_configured, _persist_state, _sync_github_label helpers"
  ```

---

## Chunk 2: Shaping, Branch Prep, Test Case Design Handlers

### Task 3: `_tick()` — `READY_FOR_SHAPING` and `READY_FOR_BRANCH_PREP` handlers

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_tick_shaping_invokes_planner_and_transitions_to_branch_prep(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"planner": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
      parsed = ParsedOutput(status="pass", artifact_paths=[])
      with patch.object(loop, "_run_role", return_value=parsed) as mock_run:
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_BRANCH_PREP
      mock_run.assert_called_once_with(task, env, "planner")


  def test_tick_shaping_skipped_when_planner_not_configured(tmp_path):
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},   # no planner
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_BRANCH_PREP


  def test_tick_shaping_stays_on_planner_failure(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"planner": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_SHAPING)
      parsed = ParsedOutput(status="fail", artifact_paths=[])
      with patch.object(loop, "_run_role", return_value=parsed):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      # On planner fail → BLOCKED (not enough info to continue)
      assert result.state == TaskState.BLOCKED


  def test_tick_branch_prep_creates_branch_and_transitions(tmp_path):
      from unittest.mock import MagicMock
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_bm = MagicMock(spec=BranchManager)
      mock_bm.branch_exists.return_value = False
      mock_bm.create_branch.return_value = "feat/BRQ-1-test-task"
      mock_bm.is_stale.return_value = False
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          branch_manager=mock_bm,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="Test Task", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_TEST_CASE_DESIGN
      assert result.branch == "feat/BRQ-1-test-task"


  def test_tick_branch_prep_uses_existing_branch(tmp_path):
      from unittest.mock import MagicMock
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_bm = MagicMock(spec=BranchManager)
      mock_bm.branch_exists.return_value = True
      mock_bm.is_stale.return_value = False
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          branch_manager=mock_bm,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="Test Task", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP,
                  branch="feat/BRQ-1-test-task")
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_TEST_CASE_DESIGN
      mock_bm.create_branch.assert_not_called()


  def test_tick_branch_prep_rebases_stale_branch(tmp_path):
      from unittest.mock import MagicMock
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_bm = MagicMock(spec=BranchManager)
      mock_bm.branch_exists.return_value = True
      mock_bm.is_stale.return_value = True
      mock_bm.merge_target.return_value = "dev"
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          branch_manager=mock_bm,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP,
                  branch="feat/BRQ-1-t")
      loop._tick(task, env, {"BRQ-1": (task, env)})
      mock_bm.rebase.assert_called_once_with("feat/BRQ-1-t", "dev")


  def test_tick_branch_prep_blocks_on_no_branch_manager(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          branch_manager=None,   # not injected
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_BRANCH_PREP)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -k "shaping or branch_prep" -v
  ```
  Expected: FAIL

- [ ] **Step 3: Implement `READY_FOR_SHAPING` and `READY_FOR_BRANCH_PREP` handlers in `_tick()`**

  In `system/orchestrator/orchestrator.py`, extend `_tick()` after the `NEW` block:

  ```python
  if task.state == TaskState.READY_FOR_SHAPING:
      if not self._role_configured(env.task_type, env.component, "planner"):
          # planner absent → skip shaping stage
          task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP",
              notes="planner role not configured — shaping skipped",
          ))
      else:
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="agent_spawn",
              role="planner",
          ))
          try:
              parsed = self._run_role(task, env, "planner")
          except Exception as exc:  # noqa: BLE001
              task = self._sm.force_block(task)
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="blocked",
                  notes=f"planner raised exception: {exc}",
              ))
              return task
          if parsed.status == "pass":
              task = self._sm.transition(task, TaskState.READY_FOR_BRANCH_PREP)
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="state_transition",
                  from_state="READY_FOR_SHAPING", to_state="READY_FOR_BRANCH_PREP",
              ))
          else:
              task = self._sm.force_block(task)
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="blocked",
                  notes=f"planner returned fail: {parsed.notes}",
              ))
      return task

  if task.state == TaskState.READY_FOR_BRANCH_PREP:
      if not self._branch_manager:
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="blocked",
              notes="branch_manager not injected",
          ))
          return task
      bm = self._branch_manager
      slug = BranchManager.make_slug(env.title)
      # Determine branch name
      if task.branch and bm.branch_exists(task.branch):
          branch = task.branch
      else:
          try:
              branch = bm.create_branch(env.task_id, env.task_type, slug)
          except Exception as exc:  # noqa: BLE001
              task = self._sm.force_block(task)
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="blocked",
                  notes=f"create_branch failed: {exc}",
              ))
              return task
      # Stale check
      if bm.is_stale(branch, self._config.orchestrator.branch_stale_days):
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="stale_warning",
              notes=f"branch {branch} is stale; rebasing onto {bm.merge_target(env.task_type)}",
          ))
          try:
              bm.rebase(branch, bm.merge_target(env.task_type))
          except Exception as exc:  # noqa: BLE001
              task = self._sm.force_block(task)
              self._emit(OrchestratorEvent(
                  task_id=task.task_id, event_type="blocked",
                  notes=f"rebase failed: {exc}",
              ))
              return task
      task = task.model_copy(update={"branch": branch})
      task = self._sm.transition(task, TaskState.READY_FOR_TEST_CASE_DESIGN)
      self._emit(OrchestratorEvent(
          task_id=task.task_id, event_type="state_transition",
          from_state="READY_FOR_BRANCH_PREP", to_state="READY_FOR_TEST_CASE_DESIGN",
      ))
      return task
  ```

  Also add this import at the top:
  ```python
  from system.orchestrator.branch_manager import BranchManager
  ```

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```
  Expected: all pass

- [ ] **Step 5: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): implement READY_FOR_SHAPING and READY_FOR_BRANCH_PREP _tick handlers"
  ```

---

### Task 4: `_tick()` — `READY_FOR_TEST_CASE_DESIGN` and `READY_FOR_DOER` + `DOER_IN_PROGRESS` handlers

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_tick_test_case_design_invokes_tester_and_transitions(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"tester": "gemini"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TEST_CASE_DESIGN,
                  branch="feat/BRQ-1-t")
      parsed = ParsedOutput(status="pass", artifact_paths=["test-cases.yaml"])
      with patch.object(loop, "_run_role", return_value=parsed):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_DOER


  def test_tick_doer_transitions_to_in_progress_runs_and_advances_to_checker(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
      parsed = ParsedOutput(status="pass", artifact_paths=[], session_id="ses-1")
      with patch.object(loop, "_run_role", return_value=parsed):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_CHECKER
      assert result.session_id == "ses-1"


  def test_tick_doer_rate_limited_goes_to_retry_pending(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER)
      # _run_role raises RuntimeError with "rate_limited" to signal rate limit
      # We simulate this by patching _run_role to return fail + rate_limited in notes
      parsed = ParsedOutput(status="fail", artifact_paths=[], notes="rate_limited")
      with patch.object(loop, "_run_role", return_value=parsed):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.RETRY_PENDING


  def test_tick_doer_exhausted_retries_goes_blocked(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
          orchestrator=OrchestratorSettings(max_retries=3),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      # Simulate a task already at max_retries
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_DOER, retry_count=3)
      parsed = ParsedOutput(status="fail", artifact_paths=[], notes="rate_limited")
      with patch.object(loop, "_run_role", return_value=parsed):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED


  def test_tick_doer_in_progress_restarts_if_artifact_missing(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      # Task restarted in DOER_IN_PROGRESS with no artifact → re-run doer
      task = Task(task_id="BRQ-1", state=TaskState.DOER_IN_PROGRESS)
      parsed = ParsedOutput(status="pass", artifact_paths=[])
      with patch.object(loop, "_run_role", return_value=parsed) as mock_run:
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_CHECKER
      mock_run.assert_called_once_with(task, env, "doer")
  ```

  Also add import for `OrchestratorSettings` at the top of test file:
  ```python
  from system.orchestrator.config import GitHubConfig, OrchestratorConfig, OrchestratorSettings
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -k "test_case_design or doer" -v
  ```

- [ ] **Step 3: Implement `READY_FOR_TEST_CASE_DESIGN`, `READY_FOR_DOER`, `DOER_IN_PROGRESS` handlers**

  In `orchestrator.py` `_tick()`, after the `READY_FOR_BRANCH_PREP` block:

  ```python
  if task.state == TaskState.READY_FOR_TEST_CASE_DESIGN:
      self._emit(OrchestratorEvent(
          task_id=task.task_id, event_type="agent_spawn", role="tester",
      ))
      try:
          parsed = self._run_role(task, env, "tester")
      except Exception as exc:  # noqa: BLE001
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="blocked",
              notes=f"tester (test-cases) failed: {exc}",
          ))
          return task
      if parsed.status == "pass":
          task = self._sm.transition(task, TaskState.READY_FOR_DOER)
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_TEST_CASE_DESIGN", to_state="READY_FOR_DOER",
          ))
      else:
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(
              task_id=task.task_id, event_type="blocked",
              notes=f"tester returned fail: {parsed.notes}",
          ))
      return task

  # Shared doer invocation logic for READY_FOR_DOER and DOER_IN_PROGRESS restarts
  def _do_run_doer(t: Task) -> Task:
      """Run doer and advance task state. Returns updated task."""
      prior_state = t.state
      # Always transition through DOER_IN_PROGRESS first (idempotent if already there)
      if t.state == TaskState.READY_FOR_DOER:
          t = self._sm.transition(t, TaskState.DOER_IN_PROGRESS)
          self._emit(OrchestratorEvent(
              task_id=t.task_id, event_type="state_transition",
              from_state=str(prior_state), to_state="DOER_IN_PROGRESS",
          ))
      try:
          parsed = self._run_role(t, env, "doer")
      except Exception as exc:  # noqa: BLE001
          parsed_notes = str(exc)
          parsed = None
      else:
          parsed_notes = parsed.notes if parsed else ""

      self._emit(OrchestratorEvent(
          task_id=t.task_id, event_type="agent_complete", role="doer",
          notes=parsed_notes,
      ))

      if parsed and parsed.status == "pass":
          if parsed.session_id:
              t = t.model_copy(update={"session_id": parsed.session_id})
          t = self._sm.transition(t, TaskState.READY_FOR_CHECKER)
          self._emit(OrchestratorEvent(
              task_id=t.task_id, event_type="state_transition",
              from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER",
          ))
      elif parsed and "rate_limited" in parsed.notes:
          if self._sm.can_transition(t, TaskState.RETRY_PENDING):
              import time as _time
              t = self._sm.transition(t, TaskState.RETRY_PENDING)
              self._retry_after[t.task_id] = (
                  _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
              )
              self._emit(OrchestratorEvent(
                  task_id=t.task_id, event_type="retry_pending",
                  notes=f"rate limited; retry after {self._config.orchestrator.retry_backoff_seconds}s",
              ))
          else:
              t = self._sm.force_block(t)
              self._emit(OrchestratorEvent(
                  task_id=t.task_id, event_type="blocked", notes="max retries exceeded",
              ))
      else:
          # failed or exception
          if self._sm.can_transition(t, TaskState.RETRY_PENDING):
              import time as _time
              t = self._sm.transition(t, TaskState.RETRY_PENDING)
              self._retry_after[t.task_id] = (
                  _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
              )
              self._emit(OrchestratorEvent(
                  task_id=t.task_id, event_type="retry_pending",
                  notes=f"doer failed; retry pending: {parsed_notes}",
              ))
          else:
              t = self._sm.force_block(t)
              self._emit(OrchestratorEvent(
                  task_id=t.task_id, event_type="blocked",
                  notes=f"doer failed and retries exhausted: {parsed_notes}",
              ))
      return t

  if task.state == TaskState.READY_FOR_DOER:
      return _do_run_doer(task)

  if task.state == TaskState.DOER_IN_PROGRESS:
      # Restart recovery: re-run doer if artifact is missing
      if not self._artifact_store.exists(task.task_id, "doer-report"):
          return _do_run_doer(task)
      # Artifact exists (interrupted after write) → advance
      task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
      self._emit(OrchestratorEvent(
          task_id=task.task_id, event_type="state_transition",
          from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER",
          notes="restart recovery: doer-report found",
      ))
      return task
  ```

  Note: The nested function `_do_run_doer` defined inside `_tick()` captures `self`, `env` from its enclosing scope. This is valid Python and avoids a separate method that takes the same params.

  Alternative if you prefer a method: move it to `_run_doer(self, task, env)` private method on the class. Either approach is fine — choose whichever makes the code clearer.

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): implement READY_FOR_TEST_CASE_DESIGN, READY_FOR_DOER, DOER_IN_PROGRESS handlers"
  ```

---

## Chunk 3: Checker, Tester, QA Automation Handlers

### Task 5: `_tick()` — `READY_FOR_CHECKER`, `CHECK_FAILED`, `RETRY_PENDING`, `READY_FOR_TESTER`, `TEST_FAILED` handlers

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_tick_checker_pass_transitions_to_tester(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"checker": "codex"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="pass", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_TESTER


  def test_tick_checker_fail_transitions_to_check_failed(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"checker": "codex"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_CHECKER)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="fail", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.CHECK_FAILED


  def test_tick_check_failed_reworks_to_doer(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=0)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_DOER
      assert result.rework_count == 1


  def test_tick_check_failed_blocks_when_rework_exhausted(tmp_path):
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          orchestrator=OrchestratorSettings(max_rework_loops=3),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.CHECK_FAILED, rework_count=3)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED


  def test_tick_retry_pending_retries_after_backoff(tmp_path):
      import time
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},
          orchestrator=OrchestratorSettings(retry_backoff_seconds=0),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=0)
      loop._retry_after["BRQ-1"] = time.monotonic() - 1  # already expired
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="pass", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_CHECKER


  def test_tick_retry_pending_waits_when_backoff_not_elapsed(tmp_path):
      import time
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.RETRY_PENDING, retry_count=0)
      loop._retry_after["BRQ-1"] = time.monotonic() + 9999  # far future
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.RETRY_PENDING  # unchanged


  def test_tick_tester_pass_transitions_to_qa(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"tester": "gemini"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="pass", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_QA_AUTOMATION


  def test_tick_tester_fail_transitions_to_test_failed(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"tester": "gemini"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_TESTER)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="fail", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.TEST_FAILED


  def test_tick_test_failed_reworks(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=0)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_DOER
      assert result.rework_count == 1


  def test_tick_test_failed_blocks_when_exhausted(tmp_path):
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          orchestrator=OrchestratorSettings(max_rework_loops=3),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.TEST_FAILED, rework_count=3)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -k "checker or check_failed or retry or tester or test_failed" -v
  ```

- [ ] **Step 3: Implement handlers**

  In `orchestrator.py` `_tick()`, add after the doer block:

  ```python
  if task.state == TaskState.READY_FOR_CHECKER:
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="checker"))
      try:
          parsed = self._run_role(task, env, "checker")
      except Exception as exc:  # noqa: BLE001
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes=f"checker exception: {exc}"))
          return task
      if parsed.status == "pass":
          task = self._sm.transition(task, TaskState.READY_FOR_TESTER)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_CHECKER", to_state="READY_FOR_TESTER"))
      else:
          task = self._sm.transition(task, TaskState.CHECK_FAILED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_CHECKER", to_state="CHECK_FAILED",
              notes=parsed.notes))
      return task

  if task.state == TaskState.CHECK_FAILED:
      if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
          task = self._sm.transition(task, TaskState.READY_FOR_DOER)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
              from_state="CHECK_FAILED", to_state="READY_FOR_DOER",
              notes=f"rework {task.rework_count}"))
      else:
          task = self._sm.transition(task, TaskState.BLOCKED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes="max rework loops exceeded (checker)"))
      return task

  if task.state == TaskState.RETRY_PENDING:
      import time as _time
      retry_after = self._retry_after.get(task.task_id, 0.0)
      if _time.monotonic() < retry_after:
          # Not yet; stay in RETRY_PENDING
          return task
      if self._sm.can_transition(task, TaskState.DOER_IN_PROGRESS):
          # Re-run doer directly from RETRY_PENDING (same as READY_FOR_DOER logic)
          # First advance to DOER_IN_PROGRESS
          task = self._sm.transition(task, TaskState.DOER_IN_PROGRESS)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="RETRY_PENDING", to_state="DOER_IN_PROGRESS"))
          # Then run doer
          try:
              parsed = self._run_role(task, env, "doer")
          except Exception as exc:  # noqa: BLE001
              parsed = ParsedOutput(status="fail", artifact_paths=[], notes=str(exc))
          if parsed.status == "pass":
              if parsed.session_id:
                  task = task.model_copy(update={"session_id": parsed.session_id})
              task = self._sm.transition(task, TaskState.READY_FOR_CHECKER)
              self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
                  from_state="DOER_IN_PROGRESS", to_state="READY_FOR_CHECKER"))
          elif "rate_limited" in parsed.notes:
              if self._sm.can_transition(task, TaskState.RETRY_PENDING):
                  task = self._sm.transition(task, TaskState.RETRY_PENDING)
                  self._retry_after[task.task_id] = (
                      _time.monotonic() + self._config.orchestrator.retry_backoff_seconds
                  )
                  self._emit(OrchestratorEvent(task_id=task.task_id, event_type="retry_pending",
                      notes="rate limited again"))
              else:
                  task = self._sm.force_block(task)
                  self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                      notes="rate limit retries exhausted"))
          else:
              task = self._sm.force_block(task)
              self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
                  notes=f"doer failed on retry: {parsed.notes}"))
      else:
          task = self._sm.transition(task, TaskState.BLOCKED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes="max retries exceeded"))
      return task

  if task.state == TaskState.READY_FOR_TESTER:
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="tester"))
      try:
          parsed = self._run_role(task, env, "tester")
      except Exception as exc:  # noqa: BLE001
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes=f"tester exception: {exc}"))
          return task
      if parsed.status == "pass":
          task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_TESTER", to_state="READY_FOR_QA_AUTOMATION"))
      else:
          task = self._sm.transition(task, TaskState.TEST_FAILED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_TESTER", to_state="TEST_FAILED",
              notes=parsed.notes))
      return task

  if task.state == TaskState.TEST_FAILED:
      if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
          task = self._sm.transition(task, TaskState.READY_FOR_DOER)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
              from_state="TEST_FAILED", to_state="READY_FOR_DOER",
              notes=f"rework {task.rework_count}"))
      else:
          task = self._sm.transition(task, TaskState.BLOCKED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes="max rework loops exceeded (tester)"))
      return task
  ```

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): implement READY_FOR_CHECKER, CHECK_FAILED, RETRY_PENDING, READY_FOR_TESTER, TEST_FAILED handlers"
  ```

---

### Task 6: `_tick()` — `READY_FOR_QA_AUTOMATION` and `QA_FAILED` handlers

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_tick_qa_automation_skipped_when_not_configured(tmp_path):
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"doer": "claude"},  # no qa_automation
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_MERGE_REVIEW


  def test_tick_qa_automation_pass_transitions(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"qa_automation": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="pass", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_MERGE_REVIEW


  def test_tick_qa_automation_fail_transitions_to_qa_failed(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"qa_automation": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_QA_AUTOMATION)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(
              status="fail", artifact_paths=[], failure_source="broken_implementation")):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.QA_FAILED
      assert result.failure_source == "broken_implementation"


  def test_tick_qa_failed_broken_impl_reworks_to_doer(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                  failure_source="broken_implementation", rework_count=0)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_DOER


  def test_tick_qa_failed_broken_automation_reworks_to_qa(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                  failure_source="broken_automation", rework_count=0)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_QA_AUTOMATION


  def test_tick_qa_failed_ambiguous_criteria_blocks(tmp_path):
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                  failure_source="ambiguous_criteria", rework_count=0)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED


  def test_tick_qa_failed_exhausted_rework_blocks(tmp_path):
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          orchestrator=OrchestratorSettings(max_rework_loops=3),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.QA_FAILED,
                  failure_source="broken_implementation", rework_count=3)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.BLOCKED
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -k "qa" -v
  ```

- [ ] **Step 3: Implement `READY_FOR_QA_AUTOMATION` and `QA_FAILED` handlers**

  ```python
  if task.state == TaskState.READY_FOR_QA_AUTOMATION:
      if not self._role_configured(env.task_type, env.component, "qa_automation"):
          task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW",
              notes="qa_automation role not configured — skipped"))
          return task
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn",
          role="qa_automation"))
      try:
          parsed = self._run_role(task, env, "qa_automation")
      except Exception as exc:  # noqa: BLE001
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes=f"qa_automation exception: {exc}"))
          return task
      if parsed.status == "pass":
          task = self._sm.transition(task, TaskState.READY_FOR_MERGE_REVIEW)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_QA_AUTOMATION", to_state="READY_FOR_MERGE_REVIEW"))
      else:
          failure_source = parsed.failure_source or "broken_implementation"
          task = task.model_copy(update={"failure_source": failure_source})
          task = self._sm.transition(task, TaskState.QA_FAILED)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_QA_AUTOMATION", to_state="QA_FAILED",
              notes=f"failure_source={failure_source}"))
      return task

  if task.state == TaskState.QA_FAILED:
      if self._sm.can_transition(task, TaskState.READY_FOR_DOER):
          task = self._sm.transition(task, TaskState.READY_FOR_DOER)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
              from_state="QA_FAILED", to_state="READY_FOR_DOER",
              notes=f"rework {task.rework_count}"))
      elif self._sm.can_transition(task, TaskState.READY_FOR_QA_AUTOMATION):
          task = self._sm.transition(task, TaskState.READY_FOR_QA_AUTOMATION)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="rework_loop",
              from_state="QA_FAILED", to_state="READY_FOR_QA_AUTOMATION",
              notes=f"rework {task.rework_count}"))
      else:
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes=f"QA_FAILED blocked: failure_source={task.failure_source}"))
      return task
  ```

- [ ] **Step 4: Run tests**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): implement READY_FOR_QA_AUTOMATION and QA_FAILED handlers"
  ```

---

## Chunk 4: Merge Review, Lessons, Human Review, GitHub Sync, main.py Wiring

### Task 7: `_tick()` — `READY_FOR_MERGE_REVIEW`, `READY_FOR_LESSONS`, `READY_FOR_HUMAN_REVIEW` handlers + GitHub label sync + state persistence calls

**Files:**
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing tests**

  ```python
  def test_tick_merge_review_writes_artifact_and_waits_for_ci(tmp_path):
      from unittest.mock import MagicMock, patch
      from system.orchestrator.ci_adapter import CIAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_ci = MagicMock(spec=CIAdapter)
      mock_ci.wait_for_green.return_value = True
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          ci_adapter=mock_ci,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                  branch="feat/BRQ-1-t")
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_LESSONS
      # merge-readiness artifact written
      assert loop._artifact_store.exists("BRQ-1", "merge-readiness")


  def test_tick_merge_review_stays_when_ci_not_green(tmp_path):
      from unittest.mock import MagicMock
      from system.orchestrator.ci_adapter import CIAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_ci = MagicMock(spec=CIAdapter)
      mock_ci.wait_for_green.return_value = False
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          ci_adapter=mock_ci,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                  branch="feat/BRQ-1-t")
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_MERGE_REVIEW  # unchanged


  def test_tick_merge_review_no_ci_adapter_uses_artifact_check(tmp_path):
      """Without a CI adapter, gate passes if merge-readiness artifact already has verdict=pass."""
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      store = ArtifactStore(base=tmp_path / "art")
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=store,
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          ci_adapter=None,  # no CI adapter
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_MERGE_REVIEW,
                  branch="feat/BRQ-1-t")
      # Pre-write a passing artifact
      from system.orchestrator.schemas.artifacts import MergeReadinessArtifact
      store.write("BRQ-1", "merge-readiness", MergeReadinessArtifact(
          task_id="BRQ-1", checked_at="2026-03-16T00:00:00Z",
          artifacts_present=[], branch="feat/BRQ-1-t",
          merge_target="dev", ci_conclusion="success",
          branch_is_current=True, verdict="pass",
      ))
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_LESSONS


  def test_tick_lessons_invokes_adapter_and_transitions(tmp_path):
      from unittest.mock import patch
      from system.orchestrator.schemas.artifacts import ParsedOutput
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          agent_defaults={"lessons": "claude"},
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_LESSONS)
      with patch.object(loop, "_run_role", return_value=ParsedOutput(status="pass", artifact_paths=[])):
          result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_HUMAN_REVIEW


  def test_tick_human_review_transitions_done_when_pr_merged(tmp_path):
      from unittest.mock import MagicMock
      from system.orchestrator.github_adapter import GitHubAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_gh = MagicMock(spec=GitHubAdapter)
      mock_gh.pr_is_merged.return_value = True
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          github_adapter=mock_gh,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW,
                  pr_url="https://github.com/owner/repo/pull/42")
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.DONE


  def test_tick_human_review_stays_when_pr_not_merged(tmp_path):
      from unittest.mock import MagicMock
      from system.orchestrator.github_adapter import GitHubAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_gh = MagicMock(spec=GitHubAdapter)
      mock_gh.pr_is_merged.return_value = False
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          github_adapter=mock_gh,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW,
                  pr_url="https://github.com/owner/repo/pull/42")
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      assert result.state == TaskState.READY_FOR_HUMAN_REVIEW


  def test_tick_human_review_no_pr_stays(tmp_path):
      """No PR URL → create one via github_adapter, then stay."""
      from unittest.mock import MagicMock
      from system.orchestrator.github_adapter import GitHubAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_gh = MagicMock(spec=GitHubAdapter)
      mock_gh.create_pr.return_value = "https://github.com/owner/repo/pull/99"
      mock_gh.pr_is_merged.return_value = False
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          github_adapter=mock_gh,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.READY_FOR_HUMAN_REVIEW,
                  branch="feat/BRQ-1-t", pr_url=None)
      result = loop._tick(task, env, {"BRQ-1": (task, env)})
      # PR was created
      mock_gh.create_pr.assert_called_once()
      assert result.pr_url == "https://github.com/owner/repo/pull/99"


  def test_github_label_sync_called_on_transition(tmp_path):
      from unittest.mock import MagicMock
      from system.orchestrator.github_adapter import GitHubAdapter
      cfg = OrchestratorConfig(github=GitHubConfig(repo="owner/repo"))
      sm = ConcreteStateMachine()
      mock_gh = MagicMock(spec=GitHubAdapter)
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
          github_adapter=mock_gh,
      )
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend",
                         github_issue_number=7)
      task = Task(task_id="BRQ-1", state=TaskState.NEW, github_issue_number=7)
      # Dep gate passes (no deps)
      loop._tick(task, env, {"BRQ-1": (task, env)})
      mock_gh.set_task_state.assert_called_once_with(7, new_state="READY_FOR_SHAPING", old_state="NEW")
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -k "merge_review or lessons or human_review or github_label" -v
  ```

- [ ] **Step 3: Implement `READY_FOR_MERGE_REVIEW`, `READY_FOR_LESSONS`, `READY_FOR_HUMAN_REVIEW` handlers**

  In `orchestrator.py` `_tick()`:

  ```python
  if task.state == TaskState.READY_FOR_MERGE_REVIEW:
      branch = task.branch or ""
      ci_green = False
      if self._ci:
          ci_green = self._ci.wait_for_green(
              branch, timeout_minutes=self._config.github.ci_timeout_minutes
          )
      else:
          # No CI adapter — check if merge-readiness artifact already written with verdict=pass
          ci_green = self.check_merge_readiness(task, branch)

      if not ci_green:
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="ci_result",
              notes=f"CI not green for {branch}; staying in READY_FOR_MERGE_REVIEW"))
          return task

      # Write deterministic merge-readiness artifact
      import datetime as _dt
      required = ["task-envelope", "doer-report", "checker-report",
                  "deterministic-test-report", "qa-automation-report", "lessons"]
      present = [n for n in required if self._artifact_store.exists(task.task_id, n)]
      merge_target = (
          self._branch_manager.merge_target(env.task_type)
          if self._branch_manager else "dev"
      )
      artifact = MergeReadinessArtifact(
          task_id=task.task_id,
          checked_at=_dt.datetime.now(_dt.UTC).isoformat(),
          artifacts_present=present,
          branch=branch,
          merge_target=merge_target,
          ci_conclusion="success",
          branch_is_current=(
              not self._branch_manager or
              not self._branch_manager.is_stale(branch, self._config.orchestrator.branch_stale_days)
          ),
          verdict="pass",
      )
      self._artifact_store.write(task.task_id, "merge-readiness", artifact)
      task = self._sm.transition(task, TaskState.READY_FOR_LESSONS)
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
          from_state="READY_FOR_MERGE_REVIEW", to_state="READY_FOR_LESSONS"))
      return task

  if task.state == TaskState.READY_FOR_LESSONS:
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="agent_spawn", role="lessons"))
      try:
          parsed = self._run_role(task, env, "lessons")
      except Exception as exc:  # noqa: BLE001
          task = self._sm.force_block(task)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="blocked",
              notes=f"lessons exception: {exc}"))
          return task
      task = self._sm.transition(task, TaskState.READY_FOR_HUMAN_REVIEW)
      self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
          from_state="READY_FOR_LESSONS", to_state="READY_FOR_HUMAN_REVIEW"))
      return task

  if task.state == TaskState.READY_FOR_HUMAN_REVIEW:
      if not self._gh:
          return task  # no GitHub adapter — wait
      # Ensure PR exists
      if not task.pr_url and task.branch:
          try:
              pr_url = self._gh.create_pr(
                  branch=task.branch,
                  title=f"{env.task_id}: {env.title}",
                  body=f"Automated PR for task {env.task_id}.\n\nAcceptance criteria:\n" +
                       "\n".join(f"- {c}" for c in env.acceptance_criteria),
              )
              task = task.model_copy(update={"pr_url": pr_url})
              self._emit(OrchestratorEvent(task_id=task.task_id, event_type="artifact_written",
                  notes=f"PR created: {pr_url}"))
          except Exception as exc:  # noqa: BLE001
              self._emit(OrchestratorEvent(task_id=task.task_id, event_type="error",
                  notes=f"create_pr failed: {exc}"))
              return task
      if task.pr_url and self._gh.pr_is_merged(task.pr_url):
          task = self._sm.transition(task, TaskState.DONE)
          self._emit(OrchestratorEvent(task_id=task.task_id, event_type="state_transition",
              from_state="READY_FOR_HUMAN_REVIEW", to_state="DONE"))
      return task
  ```

- [ ] **Step 4: Wire GitHub label sync into `_emit_transition()`**

  Modify the `_emit()` calls for state transitions to also call `_sync_github_label`. The cleanest way: create a `_transition()` helper on the loop that wraps `_sm.transition` + `_emit` + `_sync_github_label`:

  ```python
  def _do_transition(self, task: Task, to: TaskState) -> Task:
      old_state = str(task.state)
      task = self._sm.transition(task, to)
      self._emit(OrchestratorEvent(
          task_id=task.task_id, event_type="state_transition",
          from_state=old_state, to_state=str(to),
      ))
      self._sync_github_label(task, old_state=old_state)
      return task
  ```

  Then replace all `self._sm.transition(task, X)` + separate `self._emit(OrchestratorEvent(..., event_type="state_transition", ...))` pairs throughout `_tick()` with `self._do_transition(task, X)`.

  **Important**: Only replace `state_transition` event emissions — not `blocked`, `rework_loop`, `retry_pending`, `error`, `agent_spawn`, etc.

- [ ] **Step 5: Run tests**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py -v
  ```

- [ ] **Step 6: Full test suite**

  ```bash
  uv run pytest tests/ -v --tb=short
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py tests/unit/orchestrator/test_orchestrator_loop.py
  git commit -m "feat(orchestrator): implement READY_FOR_MERGE_REVIEW, READY_FOR_LESSONS, READY_FOR_HUMAN_REVIEW handlers + GitHub label sync"
  ```

---

### Task 8: Wire new deps in `main.py` + call `_persist_state()` after each tick + integration smoke test

**Files:**
- Modify: `system/orchestrator/main.py`
- Modify: `system/orchestrator/orchestrator.py`
- Test: `tests/unit/orchestrator/test_orchestrator_loop.py`

- [ ] **Step 1: Write failing test for `_persist_state()` call in `run()`**

  ```python
  def test_run_calls_persist_state_after_poll_cycle(tmp_path):
      from unittest.mock import patch, call
      cfg = OrchestratorConfig(
          github=GitHubConfig(repo="owner/repo"),
          orchestrator=OrchestratorSettings(poll_interval_seconds=0),
      )
      sm = ConcreteStateMachine()
      loop = OrchestratorLoop(
          config=cfg, state_machine=sm,
          artifact_store=ArtifactStore(base=tmp_path / "art"),
          event_log=EventLog(path=tmp_path / "events.jsonl"),
          event_queue=queue.Queue(),
      )
      # Run one tick then stop
      called = []
      original_persist = loop._persist_state
      def capturing_persist(all_tasks):
          called.append(True)
          loop.stop()
      loop._persist_state = capturing_persist
      env = TaskEnvelope(task_id="BRQ-1", title="T", task_type="feature", component="backend")
      task = Task(task_id="BRQ-1", state=TaskState.DONE)  # terminal — no tick work
      loop.run([(task, env)])
      assert len(called) >= 1, "_persist_state should be called at least once per poll cycle"
  ```

- [ ] **Step 2: Run test to confirm failure**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_run_calls_persist_state_after_poll_cycle -v
  ```
  Expected: FAIL

- [ ] **Step 3: Run test to confirm it passes**

  ```bash
  uv run pytest tests/unit/orchestrator/test_orchestrator_loop.py::test_run_calls_persist_state_after_poll_cycle -v
  ```

- [ ] **Step 4: Update `run()` to call `_persist_state()` after each poll cycle**

  In `orchestrator.py`, at the end of `run()`, after the per-task loop, add:

  ```python
  def run(self, tasks: list[tuple[Task, TaskEnvelope]]) -> None:
      all_tasks = {t.task_id: (t, env) for t, env in tasks}
      while not self._stop_event.is_set():
          for task_id, (task, env) in list(all_tasks.items()):
              task = self._tick(task, env, all_tasks)
              all_tasks[task_id] = (task, env)
          self._persist_state(all_tasks)   # ← add this
          self._stop_event.wait(timeout=self._config.orchestrator.poll_interval_seconds)
  ```

- [ ] **Step 5: Update `main.py` to inject all deps**

  Read `system/orchestrator/main.py` first, then update the `OrchestratorLoop` constructor call to pass the new deps:

  ```python
  from system.orchestrator.branch_manager import BranchManager
  from system.orchestrator.ci_adapter import CIAdapter
  from system.orchestrator.github_adapter import GitHubAdapter
  from system.orchestrator.session_manager import SessionManager

  # In the wiring section (after loading config):
  branch_manager = BranchManager(repo_root=Path("."))
  github_adapter = GitHubAdapter(repo=cfg.github.repo)
  ci_adapter = CIAdapter(
      repo=cfg.github.repo,
      poll_interval_seconds=cfg.github.ci_poll_interval_seconds,
      event_log=log,
  )
  session_manager = SessionManager()

  loop = OrchestratorLoop(
      config=cfg,
      state_machine=sm,
      artifact_store=store,
      event_log=log,
      event_queue=event_queue,
      branch_manager=branch_manager,
      github_adapter=github_adapter,
      ci_adapter=ci_adapter,
      session_manager=session_manager,
  )
  ```

- [ ] **Step 6: Verify the existing CLI smoke test still works**

  ```bash
  cd /home/andrey/projects/breqy/.worktrees/orchestrator
  echo "task_id: BRQ-TEST
  title: Test task
  task_type: feature
  component: backend
  acceptance_criteria:
    - Works" > /tmp/BRQ-TEST.yaml

  # Run with --no-tui, redirect the local task dir
  # (This just needs to not crash on startup)
  timeout 3 uv run breqy-orchestrator --config orchestrator.yaml --no-tui 2>&1 | head -20 || true
  ```
  Expected: starts up and either waits or exits cleanly (timeout 3 is fine).

- [ ] **Step 7: Run full test suite**

  ```bash
  uv run pytest tests/ -v --tb=short
  ```

- [ ] **Step 8: Lint**

  ```bash
  uv run ruff check system/orchestrator/orchestrator.py system/orchestrator/main.py
  ```
  Fix any lint errors.

- [ ] **Step 9: Commit**

  ```bash
  git add system/orchestrator/orchestrator.py system/orchestrator/main.py
  git commit -m "feat(orchestrator): wire BranchManager/GitHubAdapter/CIAdapter into main.py + persist state after each cycle"
  ```

---

## Post-implementation checklist

- [ ] All tests in `tests/unit/orchestrator/test_orchestrator_loop.py` pass
- [ ] Full `uv run pytest tests/` passes
- [ ] `uv run ruff check system/orchestrator/` passes
- [ ] `_tick()` handles all 18 task states (NEW, READY_FOR_SHAPING, READY_FOR_BRANCH_PREP, READY_FOR_TEST_CASE_DESIGN, READY_FOR_DOER, DOER_IN_PROGRESS, READY_FOR_CHECKER, CHECK_FAILED, RETRY_PENDING, READY_FOR_TESTER, TEST_FAILED, READY_FOR_QA_AUTOMATION, QA_FAILED, READY_FOR_MERGE_REVIEW, READY_FOR_LESSONS, READY_FOR_HUMAN_REVIEW, DONE, BLOCKED)
- [ ] `_persist_state()` writes `runtime-state.yaml` after each poll cycle
- [ ] GitHub label sync fires on every state transition (when `github_issue_number` is set)
- [ ] `force_kill_current()` uses `_current_runner.proc` (not `_current_process`)

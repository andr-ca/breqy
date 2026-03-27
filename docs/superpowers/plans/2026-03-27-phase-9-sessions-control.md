# Phase 9: Sessions & Control — Implementation Plan

**Created:** 2026-03-27
**Spec:** `docs/superpowers/specs/2026-03-27-phase-9-sessions-control-design.md`
**Requirements:** SES-01, SES-02, SES-03, SES-04, SES-05, SES-06, SES-07, SES-08

---

## Task Breakdown

### Task 1: ParticipantRepository + SQLite Implementation (SES-02)
**Priority:** Foundation — other tasks depend on participant tracking

**Subtasks:**
1. Add `ParticipantRepository` ABC to `breqy/storage/interfaces.py`
2. Implement `SqliteParticipantRepository` in `breqy/storage/sqlite/participant_repo.py`
3. Export from `breqy/storage/sqlite/__init__.py`
4. Tests: `tests/unit/storage/test_participant_repo.py`

**Methods:**
- `create(participant: Participant) -> None`
- `get(participant_id: str) -> Participant | None`
- `list_by_session(session_id: str) -> list[Participant]`
- `get_active_by_session(session_id: str) -> list[Participant]` (where left_at IS NULL)
- `get_by_agent_and_session(agent_id: str, session_id: str) -> Participant | None` (most recent)
- `set_left_at(participant_id: str, left_at: datetime) -> None`

**Depends on:** Nothing (uses existing `participants` table and `Participant` model)

---

### Task 2: Domain Extensions (SES-06 status, SES-07 task transitions)
**Priority:** Foundation

**Subtasks:**
1. Add `CIRCUIT_BROKEN` to `SessionStatus` enum in `breqy/domain/enums.py`
2. Add `TaskTransitionError` to `breqy/domain/errors.py` — raised when an invalid task state transition is attempted
3. Tests: extend `tests/unit/domain/test_events.py` and `tests/unit/domain/test_models.py`

**Depends on:** Nothing

---

### Task 3: AgentRegistry Session Tracking (SES-02, SES-06)
**Priority:** Foundation — control handler needs session-to-agent mapping

**Subtasks:**
1. Add `session_id: str` to `AgentInfo` dataclass
2. Add `list_by_session(session_id: str) -> list[AgentInfo]` method
3. Add `get_by_session_and_agent(session_id: str, agent_id: str) -> AgentInfo | None` method
4. Update `register()` to require `session_id`
5. Tests: extend `tests/unit/engine/test_agent_registry.py`

**Depends on:** Nothing

---

### Task 4: AgentSpawner Session Tracking + Force Kill (SES-06)
**Priority:** Foundation — circuit-break needs SIGKILL

**Subtasks:**
1. Add `session_id` tracking to `SpawnedAgent`
2. Add `force_kill(agent_dir: str) -> None` — sends SIGKILL
3. Add `force_kill_all() -> None` — SIGKILL all
4. Add `kill_by_session(session_id: str) -> None` — kill all agents for a session
5. Add `force_kill_by_session(session_id: str) -> None` — SIGKILL all agents for a session
6. Add `list_by_session(session_id: str) -> list[SpawnedAgent]`
7. Tests: extend `tests/unit/engine/test_agent_spawner.py`

**Depends on:** Nothing

---

### Task 5: SessionRepository + SessionManager Extensions (SES-01, SES-08)
**Priority:** Core — session restore depends on this

**Subtasks:**
1. Add `update_workspace_paths(session_id: str, paths: list[str]) -> None` to `SessionRepository` + SQLite impl
2. Add `restore_active_sessions() -> list[Session]` to `SessionManager` — queries all ACTIVE sessions, loads messages/tasks/participants
3. Add `set_workspace_paths(session_id: str, paths: list[str]) -> None` to `SessionManager` — validates paths exist, persists
4. Add `get_workspace_paths(session_id: str) -> list[str]` to `SessionManager`
5. Add participant lifecycle hooks: `add_participant()`, `remove_participant()`, `get_session_participants()`
6. Tests: extend `tests/unit/engine/test_session_manager.py`, extend `tests/unit/storage/test_session_repo.py` (if exists, else the sqlite test file)

**Depends on:** Task 1 (ParticipantRepository)

---

### Task 6: TaskManager — Engine-Owned Task Lifecycle (SES-07)
**Priority:** Core — control handler cancels tasks through this

**Subtasks:**
1. Create `breqy/engine/task_manager.py` with `TaskManager` class
2. Methods: `create_task()`, `update_task_status()`, `cancel_session_tasks()`, `list_tasks()`
3. Task state transition validation:
   - PENDING → RUNNING, CANCELLED
   - RUNNING → COMPLETED, FAILED, CANCELLED
   - Invalid transitions raise `TaskTransitionError`
4. Emits `TaskUpdatedEvent` on every state change
5. Tests: `tests/unit/engine/test_task_manager.py`

**Depends on:** Task 2 (TaskTransitionError)

---

### Task 7: ControlHandler — Engine-Side Control Routing (SES-03, SES-04, SES-05, SES-06)
**Priority:** Core — the main Phase 9 functionality

**Subtasks:**
1. Create `breqy/engine/control_handler.py` with `ControlHandler` class
2. Constructor takes: `session_manager`, `task_manager`, `agent_registry`, `agent_spawner`, `participant_repo`, `a2a_server`
3. `handle_control(event: ControlEvent) -> None` — main dispatch:
   - `CONTROL_STOP`: cancel tasks, forward to agents
   - `CONTROL_STOP_AND_STEER`: forward to agents (they finish atomic step), cancel pending tasks, store new_direction
   - `CONTROL_STEER`: forward to agents, store new_direction in session context
   - `CONTROL_CIRCUIT_BREAK`: force_kill all session agents, cancel tasks, mark participants left, set session CIRCUIT_BROKEN
4. Tests: `tests/unit/engine/test_control_handler.py`

**Depends on:** Tasks 3, 4, 5, 6

---

### Task 8: Agent Runtime Cooperative Cancellation (SES-03, SES-04, SES-05)
**Priority:** Core — agents must respond to control signals

**Subtasks:**
1. Add `_cancel_requested: asyncio.Event` to `AgentRuntime`
2. Add `_steer_direction: str | None` attribute
3. Add `handle_control(event: ControlEvent) -> None` method
4. Modify `handle_work()` to check `_cancel_requested` at checkpoints:
   - Before each provider stream iteration
   - After each tool call result
5. On cancel: abort streaming, send partial `MessageSentEvent`
6. On steer: store direction, agent reads it at next turn boundary
7. Add incoming message listener that routes `ControlEvent` to `handle_control()`
8. Tests: extend `tests/unit/agents/test_runtime.py`

**Depends on:** Nothing (can be built in isolation)

---

### Task 9: EngineServer Integration — Wire Everything Together (SES-01 through SES-08)
**Priority:** Integration — ties all pieces together

**Subtasks:**
1. Wire `ParticipantRepository`, `TaskManager`, `ControlHandler` into `EngineServer`
2. Update `_handle_envelope()`:
   - Control events → delegate to `ControlHandler`
   - Task events (TASK_CREATED, TASK_UPDATED) → validate via `TaskManager`, persist, broadcast
   - Agent lifecycle events → create/update Participant records
3. Add `start()` override: call `session_manager.restore_active_sessions()`, respawn agents
4. Update `_handle_disconnect()` → update participant left_at
5. Tests: extend `tests/unit/engine/test_server.py`

**Depends on:** Tasks 1–8

---

### Task 10: Workspace Boundary Enforcement in ToolService (SES-08)
**Priority:** Polish — workspace scoping for filesystem operations

**Subtasks:**
1. Add `session_id` parameter threading to `ToolService.execute_tool()`
2. Before tool execution: if session has workspace_paths, verify target paths are within workspace
3. Paths outside workspace are blocked with `PolicyDeniedError` (unless filesystem policy explicitly allows)
4. Tests: extend `tests/unit/tools/test_service.py`

**Depends on:** Task 5 (SessionManager workspace methods)

---

### Task 11: EngineDaemon Startup Restore + Agent Respawn (SES-01)
**Priority:** Integration

**Subtasks:**
1. Update `EngineDaemon.start()` to call session restore after server start
2. Auto-respawn agents for each active session's `primary_agent_id`
3. Tests: extend `tests/unit/engine/test_daemon.py`

**Depends on:** Tasks 5, 9

---

### Task 12: Integration Tests (SES-01 through SES-08)
**Priority:** Verification

**Subtasks:**
1. `tests/integration/engine/test_control_flow.py` — end-to-end control signal tests
2. `tests/integration/engine/test_session_restore.py` — restart survival test
3. `tests/integration/engine/test_task_lifecycle.py` — agent proposes task, engine validates

**Depends on:** Tasks 1–11

---

## Execution Order

```
Phase   Tasks              Description
  A     1, 2, 3, 4, 8     Foundation (all independent, can be parallelized)
  B     5, 6               Core services (depend on Phase A)
  C     7                  Control handler (depends on Phase B)
  D     9, 10, 11          Integration wiring (depends on Phase C)
  E     12                 Integration tests (depends on Phase D)
```

---

## Estimated Scope
- **New files:** 7 production + 7 test files
- **Modified files:** ~12 existing files
- **Test count estimate:** ~80-120 new tests

---
*Plan created: 2026-03-27*

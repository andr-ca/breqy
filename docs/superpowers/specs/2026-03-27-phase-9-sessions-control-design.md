# Phase 9: Sessions & Control — Design Spec

**Created:** 2026-03-27
**Phase goal:** Sessions are durable and controllable — they survive restarts, track all participants, and respond immediately to user control signals (stop, stop-and-steer, steer, circuit-break) while maintaining canonical task state and workspace scoping.

**Requirements:** SES-01, SES-02, SES-03, SES-04, SES-05, SES-06, SES-07, SES-08

---

## 1. Overview

Phase 9 builds on the engine daemon (Phase 5), agent runtime (Phase 8), and storage layer (Phase 2) to add four capabilities:

1. **Session persistence and restart survival** — active sessions rehydrate from DB on engine startup; TUI reconnects resume without data loss
2. **Participant tracking** — `ParticipantRepository` and engine-level join/leave lifecycle management
3. **Control primitives** — four control signals with distinct semantics, engine-side routing, and agent-side cooperative cancellation
4. **Canonical task state** — engine owns task lifecycle; agents propose task changes via events; user steering modifies tasks mid-flight
5. **Workspace scoping** — sessions bind to workspace paths; filesystem operations respect workspace boundaries

---

## 2. SES-01: Session Persistence Across Restart

### What exists
- `Session` model with `workspace_paths`, `status`, `primary_agent_id`
- `SqliteSessionRepository` with `create()`, `get()`, `list_active()`, `update_status()`
- `SessionManager` with `create_session()`, `get_session()`, `list_sessions()`, `close_session()`
- Sessions are stored in SQLite with WAL mode

### What's missing
- Engine startup doesn't rehydrate sessions from DB
- `SessionManager` has no `resume_session()` or `restore_all()` method
- In-memory state (AgentRegistry subscriptions) isn't rebuilt on restart
- No `SESSION_RESUMED` event emission on reconnect

### Design

**On engine startup (`EngineDaemon.start()` / `EngineServer.start()`):**
1. After migrations run, call `SessionManager.restore_active_sessions()`
2. This queries `SessionRepository.list_active()` and loads each session's messages, tasks, and participants into the session manager's in-memory cache
3. Sessions remain in `ACTIVE` status — they survive the restart gap
4. Connected agents are NOT present (they must reconnect); `AgentRegistry` starts empty
5. Emit `SessionResumedEvent` for each restored session (but only internally to the event bus, not broadcast — no clients yet)

**On TUI reconnect:**
1. TUI connects to engine via A2A socket
2. Sends a `SessionResumedEvent` with the `session_id` it wants to resume
3. Engine validates session exists and is active, subscribes the TUI client to that session's events
4. Responds with current session state (message history, task list, participants)
5. TUI renders from the state snapshot, then receives live events going forward

**On agent reconnect after restart:**
1. Agent spawner restarts agents for all active sessions (after session restore)
2. Agent connects, sends `AGENT_CONNECTED` lifecycle event
3. Engine re-registers agent in `AgentRegistry` and updates `Participant.left_at` → None (or creates a new participant record for the new connection span)

### Session state transitions

```
ACTIVE --[close]--> CLOSED
ACTIVE --[circuit_break]--> CIRCUIT_BROKEN   (new status)
ACTIVE --[engine restart]--> ACTIVE           (survives)
ACTIVE --[suspend]--> SUSPENDED               (future: explicit park)
```

**New enum value:** Add `CIRCUIT_BROKEN` to `SessionStatus`.

---

## 3. SES-02: Participant Tracking

### What exists
- `Participant` model: `id`, `session_id`, `agent_id`, `joined_at`, `left_at`
- `participants` DB table with FK to sessions, index on session_id
- `AgentRegistry` tracks agents in memory (no session association)

### What's missing
- `ParticipantRepository` interface
- `SqliteParticipantRepository` implementation
- Participant lifecycle management in engine server
- AgentRegistry → session association

### Design

**`ParticipantRepository` interface (in `storage/interfaces.py`):**
```python
class ParticipantRepository(ABC):
    async def create(self, participant: Participant) -> None: ...
    async def get(self, participant_id: str) -> Participant | None: ...
    async def list_by_session(self, session_id: str) -> list[Participant]: ...
    async def set_left_at(self, participant_id: str, left_at: datetime) -> None: ...
    async def get_active_by_session(self, session_id: str) -> list[Participant]: ...
    async def get_by_agent_and_session(self, agent_id: str, session_id: str) -> Participant | None: ...
```

**`SqliteParticipantRepository`** — standard CRUD against the existing `participants` table.

**Engine-level lifecycle:**
- On `AGENT_CONNECTED`: create a `Participant` record with `joined_at=now`, `left_at=None`. Associate agent_id with session_id in the registry.
- On `AGENT_DISCONNECTED` / disconnect callback: set `Participant.left_at=now`.
- On circuit-break: set `left_at=now` for all active participants in the session.

**`AgentInfo` extension:**
```python
@dataclass
class AgentInfo:
    agent_id: str
    client_id: str
    session_id: str      # NEW — which session this agent belongs to
    pid: int | None = None
```

This lets `AgentRegistry` answer "which agents are in session X?" and "which session does this agent belong to?".

---

## 4. SES-03 through SES-06: Control Primitives

### Existing infrastructure
- `ControlEvent` with `event_type` field supporting all four control types
- `ControlEvent.new_direction: str = ""` for steer/stop-and-steer
- `EVENT_TYPE_MAP` routes control event types to `ControlEvent` class
- `AgentSpawner.kill()` sends SIGTERM
- `AgentRuntime.handle_work()` has no cancellation mechanism

### Design: Engine-Side Control Handler

Add a `ControlHandler` service (or inline in `EngineServer._handle_envelope()`) that processes control events:

```
ControlEvent received
  ├── CONTROL_STOP
  │   ├── Set session.active_control = "stop"
  │   ├── Cancel all running tasks → TaskStatus.CANCELLED
  │   ├── Forward ControlEvent to all agents in session
  │   └── Session remains ACTIVE (user can send new message)
  │
  ├── CONTROL_STOP_AND_STEER
  │   ├── Set session.active_control = "stop_and_steer"
  │   ├── Forward ControlEvent to all agents in session (agent will finish atomic step then stop)
  │   ├── Cancel PENDING tasks; mark RUNNING tasks as CANCELLED after agent acknowledges
  │   └── new_direction is stored; next user message (or the direction itself) starts a new plan
  │
  ├── CONTROL_STEER
  │   ├── Forward ControlEvent to all agents in session
  │   ├── Agent continues current step, then reads updated context
  │   └── new_direction is injected into session context for next agent turn
  │
  └── CONTROL_CIRCUIT_BREAK
      ├── Hard-kill all agent processes for this session (SIGKILL)
      ├── Set all running tasks → CANCELLED
      ├── Set all participant left_at = now
      ├── Set session.status = CIRCUIT_BROKEN
      ├── Record emergency termination timestamp
      └── Broadcast SessionClosedEvent (or a new CircuitBreakEvent)
```

### Design: Agent-Side Cooperative Cancellation

The agent runtime's `handle_work()` loop must become **cancellation-aware**:

1. Add an `asyncio.Event` called `_cancel_requested` on `AgentRuntime`
2. Add a `_steer_direction: str | None` attribute
3. The runtime listens for incoming `ControlEvent` messages (via the A2A client's message stream) while also running the work loop
4. At each cancellation checkpoint (between tool calls, between provider streaming chunks), check `_cancel_requested`
5. On **stop**: set `_cancel_requested`, abort streaming, send final `MessageSentEvent` with partial content
6. On **stop-and-steer**: set `_cancel_requested` after current atomic step (tool call) completes
7. On **steer**: set `_steer_direction` — agent picks it up at the next turn boundary and incorporates it into context
8. On **circuit-break**: the process is SIGKILL'd by engine; no cooperative handling needed

**Cancellation checkpoints in `handle_work()`:**
- Before each provider streaming iteration
- After each tool call result is received
- These are natural "atomic step boundaries"

### `AgentSpawner` extensions

```python
class AgentSpawner:
    def kill(self, agent_dir: str) -> None:
        """Graceful termination (SIGTERM)."""
        ...

    def force_kill(self, agent_dir: str) -> None:
        """Hard kill (SIGKILL) for circuit-break."""
        ...

    def force_kill_all(self) -> None:
        """SIGKILL all spawned agents."""
        ...

    def kill_by_session(self, session_id: str) -> None:
        """Kill all agents associated with a session."""
        ...
```

This requires `SpawnedAgent` to track `session_id`.

---

## 5. SES-07: Engine Owns Canonical Task State

### What exists
- `Task` model and `TaskRepository` with `create()`, `get()`, `list_by_session()`, `update_status()`
- `TaskUpdatedEvent` with `task_id`, `title`, `status`

### What's missing
- Engine-side task lifecycle manager
- Agent task proposal protocol
- Task update validation (engine validates before persisting)
- User steering can modify tasks

### Design

**`TaskManager` service (new, in `breqy/engine/task_manager.py`):**
```python
class TaskManager:
    def __init__(self, task_repo: TaskRepository, event_bus: EventBus):
        ...

    async def create_task(self, session_id: str, title: str, description: str = "",
                          parent_id: str | None = None, agent_id: str | None = None) -> Task:
        """Create a task. Engine validates and persists. Returns canonical Task."""

    async def update_task_status(self, task_id: str, new_status: TaskStatus,
                                 agent_id: str | None = None) -> Task:
        """Update task status with validation. Invalid transitions are rejected."""

    async def cancel_session_tasks(self, session_id: str) -> list[Task]:
        """Cancel all pending/running tasks in a session (for stop/circuit-break)."""

    async def list_tasks(self, session_id: str) -> list[Task]:
        """Return canonical task list for a session."""
```

**Task state transitions (validated by engine):**
```
PENDING → RUNNING → COMPLETED
PENDING → CANCELLED
RUNNING → COMPLETED
RUNNING → FAILED
RUNNING → CANCELLED
```

Invalid transitions (e.g., `COMPLETED → RUNNING`) raise a `ValueError`.

**Agent task proposal protocol:**
- Agent sends a `TaskUpdatedEvent` with `event_type=TASK_CREATED` or `TASK_UPDATED`
- Engine's `_handle_envelope()` intercepts these events
- Engine validates (task exists, transition is valid, agent has permission)
- Engine persists the canonical state and broadcasts the validated `TaskUpdatedEvent`
- If validation fails, engine sends an error event back to the agent

**User steering modifies tasks:**
- On `CONTROL_STOP`: `TaskManager.cancel_session_tasks(session_id)`
- On `CONTROL_STOP_AND_STEER`: cancel pending tasks; running tasks cancelled after agent acknowledges
- On `CONTROL_STEER`: no task cancellation — direction is updated in context

---

## 6. SES-08: Workspace Scoping

### What exists
- `Session.workspace_paths: list[str]` field
- `SessionCreatedEvent.workspace` field
- SQLite stores workspace_paths as JSON
- `FilesystemPolicyChecker` evaluates path rules but doesn't consult session workspaces

### What's missing
- Workspace attach/detach operations
- Default workspace from session creation
- Workspace boundary enforcement in tool execution
- Integration with filesystem policy

### Design

**Workspace management in `SessionManager`:**
```python
async def set_workspace_paths(self, session_id: str, paths: list[str]) -> None:
    """Attach workspace paths to a session. Validates paths exist."""

async def get_workspace_paths(self, session_id: str) -> list[str]:
    """Return workspace paths for a session."""
```

**`SessionRepository` extension:**
```python
async def update_workspace_paths(self, session_id: str, paths: list[str]) -> None: ...
```

**Workspace boundary enforcement:**
- When a tool (ShellTool, FilesystemTool) executes, the engine checks that target paths fall within session workspace boundaries
- Paths outside workspaces are evaluated against filesystem policy as usual
- If workspace_paths is empty, no workspace scoping is applied (backward-compatible)
- Workspace scoping is additive to (not replacing) filesystem policy — both must permit the operation

**Integration point:** `ToolService.execute_tool()` checks workspace paths before delegating to the tool executor.

---

## 7. New/Modified Components Summary

### New files
| File | Purpose |
|------|---------|
| `breqy/engine/task_manager.py` | Engine-owned task lifecycle management |
| `breqy/engine/control_handler.py` | Control event processing logic |
| `breqy/storage/sqlite/participant_repo.py` | SQLite participant repository |
| `tests/unit/engine/test_task_manager.py` | Task manager tests |
| `tests/unit/engine/test_control_handler.py` | Control handler tests |
| `tests/unit/storage/test_participant_repo.py` | Participant repo tests |
| `tests/unit/engine/test_session_restore.py` | Session restore/restart tests |
| `tests/integration/engine/test_control_flow.py` | End-to-end control flow tests |

### Modified files
| File | Changes |
|------|---------|
| `breqy/domain/enums.py` | Add `CIRCUIT_BROKEN` to `SessionStatus` |
| `breqy/storage/interfaces.py` | Add `ParticipantRepository`, extend `SessionRepository`, extend `TaskRepository` |
| `breqy/storage/sqlite/__init__.py` | Export new repos |
| `breqy/engine/agent_registry.py` | Add `session_id` to `AgentInfo`, add session query methods |
| `breqy/engine/agent_spawner.py` | Add `force_kill()`, `force_kill_all()`, session tracking |
| `breqy/engine/session_manager.py` | Add `restore_active_sessions()`, `set_workspace_paths()`, participant integration |
| `breqy/engine/server.py` | Add control event handling, task event validation, participant lifecycle, session restore on start |
| `breqy/engine/daemon.py` | Call session restore on startup, respawn agents for active sessions |
| `breqy/agents/runtime.py` | Add cooperative cancellation, control event listener, steer handling |
| `breqy/tools/service.py` | Add workspace boundary check |

---

## 8. Event Flow Diagrams

### Control: Stop
```
TUI → ControlEvent(CONTROL_STOP) → Engine
  Engine:
    → cancel_session_tasks(session_id)
    → forward ControlEvent to agents
  Agent:
    → sets _cancel_requested
    → aborts at next checkpoint
    → sends partial MessageSentEvent
  TUI:
    → receives task cancellation events
    → session is idle, user can type
```

### Control: Circuit-Break
```
TUI → ControlEvent(CONTROL_CIRCUIT_BREAK) → Engine
  Engine:
    → force_kill all session agents (SIGKILL)
    → cancel_session_tasks(session_id)
    → set participant left_at = now
    → set session.status = CIRCUIT_BROKEN
    → broadcast SessionClosedEvent
  TUI:
    → receives session closed event
    → shows circuit-broken status
```

### Session Restart Survival
```
Engine crash/restart:
  1. EngineDaemon.start()
  2. Migrations run (idempotent)
  3. SessionManager.restore_active_sessions()
     → loads all ACTIVE sessions from DB
  4. For each session: load messages, tasks, participants
  5. Spawn agents for active sessions
  6. Agents connect, register, get re-associated
  7. TUI reconnects → SessionResumedEvent → full state returned
```

---

## 9. Open Questions for User

1. **Circuit-broken sessions: recoverable?** Should a circuit-broken session be resumable (allowing user to restart agents), or is it terminal like CLOSED? **Recommendation:** Terminal — user creates a new session if needed. Simpler and safer.

2. **Agent respawn on restart: automatic or manual?** When the engine restarts and finds active sessions, should it automatically respawn agents, or wait for a TUI to reconnect and request it? **Recommendation:** Automatic — the engine is "always-on" and should restore its full state autonomously.

3. **Steer context injection:** How should the steer direction be delivered to the agent? Options:
   a. As a system message prepended to the next inference call
   b. As a separate field in `AgentWorkRequestedEvent`
   c. Both (system message for immediate context, field for structured access)
   **Recommendation:** (a) — simplest and most natural; the agent sees it as context.

4. **Workspace validation:** Should `set_workspace_paths()` validate that paths exist on disk, or just store them? **Recommendation:** Validate at attachment time — prevents misconfigured sessions.

---

## 10. Success Criteria Mapping

| Criterion | Design Coverage |
|-----------|----------------|
| SES-01: TUI reconnect resumes with full history | `restore_active_sessions()` + `SessionResumedEvent` protocol |
| SES-02: Participant tracking with timestamps | `ParticipantRepository` + engine lifecycle hooks |
| SES-03: Stop cancels active work within one event cycle | Control handler + cooperative cancellation in runtime |
| SES-04: Stop-and-steer: atomic step finishes, plan halts, new direction accepted | `_cancel_requested` after tool completion + `new_direction` storage |
| SES-05: Steer updates context mid-flight | `_steer_direction` attribute + system message injection |
| SES-06: Circuit-break hard-kills all processes | `force_kill()` with SIGKILL + `CIRCUIT_BROKEN` status |
| SES-07: Engine owns task state; agents propose | `TaskManager` validates transitions; engine persists canonical state |
| SES-08: Workspace scoping | `set_workspace_paths()` + `ToolService` boundary check |

---
*Spec created: 2026-03-27*

# Observability & Logging — Design Spec

**Date:** 2026-03-28
**Status:** Implemented (verified 2026-08-19)
**Branch:** exp-full-build

> **Implementation status (2026-08-19):** The substantive design is landed and
> verified in-tree. `setup_logging()` is extended for per-process JSON log files;
> structlog is adopted across all processes (including the former stdlib users
> `a2a/server.py`, `a2a/client.py`, and `tui/app.py`); agent-subprocess output
> handling is fixed in `engine/agent_spawner.py`; the LogsScreen ring buffer is
> moved to `BreqyApp._log_buffer`; and the dual-view (Events/Logs) `LogsScreen`
> with a `Tab` toggle is implemented. The engine daemon, agent runtime, and TUI
> all call `setup_logging()` at startup.

## Problem

Breqy is a multi-process system (engine daemon + agent subprocesses + TUI) communicating over Unix socket A2A protocol. When things go wrong, there is almost no way to trace what happened:

- The agent runtime has **zero logging**. No imports, no calls, nothing.
- Agent subprocess stderr is piped to `subprocess.PIPE` but **never read** — output is silently discarded (and if the pipe buffer fills, the agent hangs).
- The engine uses structlog; the A2A layer and TUI use stdlib `logging` — but stdlib is **never configured**, so those messages go nowhere.
- There are no DEBUG-level log calls anywhere, so increasing verbosity reveals nothing.
- The TUI LogsScreen only captures domain events while it's mounted. Events that arrive when the screen is closed are lost.
- No correlation IDs thread through the system, making it impossible to trace a single user message from TUI → engine → agent → response → TUI.
- No log files — everything goes to stderr, which is lost in daemon mode.

## Architecture

### Principle: One backend, all processes

Standardize on **structlog** everywhere. Drop stdlib `logging` from the 3 files that use it (`a2a/server.py`, `a2a/client.py`, `tui/app.py`). Every process calls `setup_logging()` at startup.

### Three log destinations

| Destination | Format | Purpose |
|-------------|--------|---------|
| **File** | JSON lines | Machine-parseable, persistent. One file per process in `.breqy/logs/`. |
| **Stderr** | Console (human-readable) | Foreground debugging. Suppressed in daemon mode and TUI mode. |
| **TUI LogsScreen** | Rendered entries | Live visibility. Background buffer in App, survives screen push/pop. |

### Log file layout

```
.breqy/logs/
├── engine.log           # Engine daemon
├── agent-breqy.log      # Agent "breqy" subprocess
├── agent-{id}.log       # Other agents
└── tui.log              # TUI process
```

JSON lines format:
```json
{"ts":"2026-03-28T14:30:00.123Z","level":"info","event":"Envelope received","session_id":"ses_abc","agent_id":"breqy","process":"engine","module":"server","event_type":"MessageSentEvent"}
```

No log rotation in v1 — files are append-only. Rotation can be added later.

### Correlation

Bind `session_id` and `agent_id` to structlog context vars at request boundaries:
- Engine: when handling an envelope, bind sender's session/agent context
- Agent: when receiving work, bind session_id from the work request
- TUI: when sending a message, bind the active session_id

Every log entry inherits these automatically via `merge_contextvars`.

## Process-Specific Setup

### Engine daemon

```python
# daemon.py:start()
setup_logging(level=config.log_level, log_dir=data_dir / "logs", process="engine")
```

- File: `.breqy/logs/engine.log` (JSON)
- Stderr: console renderer (existing behavior)
- Binds `process="engine"` to context

### Agent subprocess

```python
# runtime.py:main()
setup_logging(level=agent_config.log_level, log_dir=data_dir / "logs", process="agent", agent_id=agent_id)
```

- File: `.breqy/logs/agent-{agent_id}.log` (JSON)
- Stderr: written to file (no console in subprocess)
- Binds `process="agent"`, `agent_id=...` to context
- Uses `AgentConfig.log_level` and `AgentConfig.log_path` which are already declared but never consumed

### Agent subprocess output capture

Current `AgentSpawner.spawn()` uses `stdout=subprocess.PIPE, stderr=subprocess.PIPE` but never reads from the pipes. Fix:
- `stdout=subprocess.DEVNULL` (agent uses A2A, not stdout)
- `stderr=subprocess.DEVNULL` (agent writes its own log file now)

If we want engine-side visibility of agent errors, `AgentSpawner` can instead redirect stderr to the agent's log file path.

### TUI process

```python
# app.py or cli.py tui command
setup_logging(level=config.log_level, log_dir=data_dir / "logs", process="tui")
```

- File: `.breqy/logs/tui.log` (JSON)
- Stderr: **suppressed** (would corrupt terminal)
- Extra processor: pushes entries into the App's background log buffer for LogsScreen

## setup_logging() Enhancement

The existing `breqy/utils/logging.py:setup_logging(level)` must be extended:

```python
def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    process: str = "engine",
    agent_id: str = "",
) -> None:
```

Processors chain:
1. `merge_contextvars` (existing)
2. `add_log_level` (existing)
3. `StackInfoRenderer` (existing)
4. `set_exc_info` (existing)
5. `TimeStamper(fmt="iso")` (existing)
6. **NEW:** `add_process_info` — adds `process`, `agent_id`, `module` keys
7. **Fork:**
   - File handler → `JSONRenderer` → append to log file
   - Stderr → `ConsoleRenderer` (if not suppressed)
   - TUI handler → push to App buffer (if TUI mode)

## Instrumentation Plan

### Tier 1 — Message flow (DEBUG level)

These are the calls that trace a single user message through the full lifecycle. Running with `--log-level DEBUG` should produce a complete trace.

| Step | File | Event | Key fields |
|------|------|-------|------------|
| User presses Enter | `tui/app.py` | `"User message submitted"` | session_id, content_length |
| TUI sends to engine | `tui/app.py` | `"Sending event to engine"` | session_id, message_id, event_type |
| Engine receives envelope | `engine/server.py` | `"Envelope received"` | client_id, event_type, session_id |
| Engine routes envelope | `engine/server.py` | `"Routing envelope"` | handler, event_type |
| User message persisted | `engine/server.py` | `"Message persisted"` | session_id, message_id |
| Work dispatched to agent | `engine/server.py` | `"Work dispatched"` | session_id, agent_id, message_count |
| Event broadcast | `engine/server.py` | `"Event broadcast"` | event_type, exclude_client, recipient_count |
| Agent receives work | `agents/runtime.py` | `"Work received"` | session_id, message_count |
| Provider stream start | `agents/runtime.py` | `"Provider stream started"` | provider, model |
| Chunk sent | `agents/runtime.py` | `"Chunk sent"` | message_id, chunk_index |
| Agent response complete | `agents/runtime.py` | `"Response complete"` | message_id, content_length |
| TUI receives event | `tui/app.py` | `"Event received"` | event_type, session_id |
| TUI dispatches to screen | `tui/app.py` | `"Dispatched to screen"` | handler_name |

### Tier 2 — Lifecycle (INFO level)

| Step | File | Event |
|------|------|-------|
| Agent runtime started/stopped | `agents/runtime.py` | `"Agent runtime started/stopped"` |
| Agent registered/unregistered | `engine/agent_registry.py` | `"Agent registered/unregistered"` |
| Agent connect/disconnect | `a2a/server.py` | Already exists |
| Agent spawned/terminated | `engine/agent_spawner.py` | Already exists |
| Session created/closed | `engine/session_manager.py` | Already exists |
| A2A connection established | `a2a/client.py` | Already exists |

### Tier 3 — Errors (WARNING/ERROR)

Mostly already covered. Add:
- Envelope deserialization failures (`a2a/envelope.py`)
- Provider stream errors (`agents/runtime.py`)
- A2A transport errors (`a2a/transport.py`)

## TUI LogsScreen Enhancement

### Background buffer

Move the event ring buffer from `LogsScreen` into `BreqyApp`:

```python
class BreqyApp(App):
    def __init__(self, ...):
        ...
        self._log_buffer: deque[LogEntry] = deque(maxlen=1000)
```

All events (domain + Python log entries) are appended to `_log_buffer` regardless of whether LogsScreen is mounted. When LogsScreen mounts, it reads the existing buffer and subscribes to new entries.

### Dual view

LogsScreen gets two tabs/modes:
- **Events** — domain events (existing behavior)
- **Logs** — Python log entries from the TUI process structlog handler

User toggles with a key binding (e.g., `Tab`).

### Filter enhancement

In addition to event_type prefix filtering:
- Filter by `session_id`
- Filter by `agent_id`
- Filter by log level (show only WARNING+)

## stdlib → structlog Migration

Replace stdlib `logging` in these 3 files:

| File | Current | Change to |
|------|---------|-----------|
| `breqy/a2a/server.py` | `logging.getLogger(__name__)` | `structlog.get_logger(__name__)` |
| `breqy/a2a/client.py` | `logging.getLogger(__name__)` | `structlog.get_logger(__name__)` |
| `breqy/tui/app.py` | `logging.getLogger(__name__)` | `structlog.get_logger(__name__)` |

Update all `.warning(msg, arg1, arg2)` style calls to structlog's `.warning(msg, key=value)` style.

## Files to Modify

### New files
- None — all changes are to existing files

### Modified files

| File | Changes |
|------|---------|
| `breqy/utils/logging.py` | Extended `setup_logging()` with file handler, process mode, JSON renderer |
| `breqy/agents/runtime.py` | Add structlog import, logger, calls at all Tier 1/2 points, call `setup_logging()` in `main()` |
| `breqy/engine/server.py` | Add DEBUG-level Tier 1 calls (envelope receive, route, broadcast) |
| `breqy/engine/daemon.py` | Pass `log_dir` to `setup_logging()` |
| `breqy/engine/agent_spawner.py` | Change subprocess stdout/stderr handling |
| `breqy/engine/agent_registry.py` | Add structlog logger with INFO-level register/unregister |
| `breqy/a2a/server.py` | Migrate stdlib → structlog |
| `breqy/a2a/client.py` | Migrate stdlib → structlog |
| `breqy/a2a/transport.py` | Add structlog logger with DEBUG-level frame tracing |
| `breqy/a2a/envelope.py` | Add structlog logger with WARNING-level deserialization errors |
| `breqy/tui/app.py` | Migrate stdlib → structlog, add Tier 1 calls, move log buffer to App |
| `breqy/tui/screens/logs.py` | Read from App buffer, add dual view, add filter enhancements |
| `breqy/tui/screens/chat.py` | Add DEBUG-level dispatch logging |
| `breqy/cli.py` | Call `setup_logging()` for TUI command |
| `breqy/config/settings.py` | Ensure `log_dir` is derived from `data_dir` |

## Success Criteria

1. Running `breqy engine start --log-level DEBUG` produces a complete trace of a user message from TUI → engine → agent → response → TUI in `.breqy/logs/engine.log`
2. Agent subprocess logs appear in `.breqy/logs/agent-breqy.log`
3. TUI logs appear in `.breqy/logs/tui.log`
4. `Ctrl+L` in TUI shows events that occurred before the screen was opened
5. All 3 files that used stdlib `logging` now use structlog
6. All existing tests pass — no regressions

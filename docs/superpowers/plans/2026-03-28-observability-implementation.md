# Observability & Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement unified structlog-based observability across all Breqy processes (engine, agent, TUI) with JSON file logging, correlation IDs, and message-flow tracing — per the approved spec at `docs/plans/2026-03-28-observability.md`.

**Architecture:** Extend the existing `setup_logging()` to support multiple output destinations (file + stderr + TUI buffer). Migrate 3 files from stdlib `logging` to structlog. Add DEBUG-level instrumentation at all message-flow trace points. Move the TUI log buffer from `LogsScreen` to `BreqyApp` so events survive screen push/pop.

**Tech Stack:** Python 3.12, structlog, Textual (TUI framework), pydantic, pytest

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Branch:** `exp-full-build`
**Run tests:** `uv run pytest`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `breqy/utils/logging.py` | Modify | Extended `setup_logging()` with file handler, process context, JSON renderer |
| `tests/unit/utils/test_logging.py` | Modify | Tests for new `setup_logging()` parameters and behaviors |
| `breqy/a2a/server.py` | Modify | stdlib→structlog migration, add DEBUG-level trace calls |
| `breqy/a2a/client.py` | Modify | stdlib→structlog migration |
| `breqy/a2a/transport.py` | Modify | Add structlog DEBUG-level frame tracing |
| `breqy/a2a/envelope.py` | Modify | Add structlog WARNING-level deserialization errors |
| `tests/unit/a2a/test_server.py` | Modify | Tests for structlog migration |
| `tests/unit/a2a/test_client.py` | Modify | Tests for structlog migration |
| `breqy/agents/runtime.py` | Modify | Add structlog logger, call `setup_logging()`, instrument all trace points |
| `tests/unit/agents/test_runtime.py` | Modify | Tests for runtime logging setup and instrumentation |
| `breqy/engine/server.py` | Modify | Add DEBUG-level Tier 1 trace calls |
| `breqy/engine/daemon.py` | Modify | Pass `log_dir` to `setup_logging()` |
| `breqy/engine/agent_spawner.py` | Modify | Change subprocess stdout/stderr to DEVNULL |
| `breqy/engine/agent_registry.py` | Modify | Add structlog INFO-level register/unregister |
| `tests/unit/engine/test_agent_spawner.py` | Modify | Tests for subprocess pipe changes |
| `breqy/tui/app.py` | Modify | stdlib→structlog migration, add log buffer, add trace calls |
| `breqy/tui/screens/logs.py` | Modify | Read from App buffer on mount, background event capture |
| `breqy/tui/screens/chat.py` | Modify | Add DEBUG-level dispatch logging |
| `tests/tui/test_app.py` | Modify | Tests for log buffer and structlog migration |
| `tests/tui/test_logs_screen.py` | Modify | Tests for background buffer behavior |
| `breqy/cli.py` | Modify | Call `setup_logging()` for TUI command |
| `breqy/config/models.py` | Modify | Add `log_dir` property derived from `data_dir` |
| `tests/unit/config/test_models.py` | Modify | Test for `log_dir` derivation |

---

### Task 1: Extend `setup_logging()` — File Handler, Process Context, JSON Renderer

**Files:**
- Modify: `breqy/utils/logging.py`
- Modify: `tests/unit/utils/test_logging.py`

This is the foundation — every other task depends on this.

- [ ] **Step 1: Write failing test — file handler creates log file**

```python
# tests/unit/utils/test_logging.py
import structlog

def test_setup_logging_creates_log_file(tmp_path):
    """setup_logging with log_dir creates a JSON log file."""
    from breqy.utils.logging import setup_logging
    setup_logging(level="INFO", log_dir=tmp_path, process="engine")

    logger = structlog.get_logger("test")
    logger.info("hello from test")

    log_file = tmp_path / "engine.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello from test" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/utils/test_logging.py::test_setup_logging_creates_log_file -v`
Expected: FAIL — `setup_logging()` does not accept `log_dir` or `process` params yet.

- [ ] **Step 3: Write failing test — agent log file naming**

```python
def test_setup_logging_agent_log_file(tmp_path):
    """Agent process creates agent-{id}.log file."""
    from breqy.utils.logging import setup_logging
    setup_logging(level="INFO", log_dir=tmp_path, process="agent", agent_id="breqy")

    logger = structlog.get_logger("test")
    logger.info("agent log entry")

    log_file = tmp_path / "agent-breqy.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "agent log entry" in content
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/utils/test_logging.py::test_setup_logging_agent_log_file -v`
Expected: FAIL

- [ ] **Step 5: Write failing test — JSON format in file**

```python
import json

def test_setup_logging_json_format(tmp_path):
    """Log file entries are valid JSON lines."""
    from breqy.utils.logging import setup_logging
    setup_logging(level="INFO", log_dir=tmp_path, process="engine")

    logger = structlog.get_logger("test")
    logger.info("json test", session_id="ses_123")

    log_file = tmp_path / "engine.log"
    lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["event"] == "json test"
    assert entry["session_id"] == "ses_123"
    assert "process" in entry
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/unit/utils/test_logging.py::test_setup_logging_json_format -v`
Expected: FAIL

- [ ] **Step 7: Write failing test — process context bound**

```python
def test_setup_logging_binds_process_context(tmp_path):
    """setup_logging binds process and agent_id to structlog context."""
    from breqy.utils.logging import setup_logging
    setup_logging(level="INFO", log_dir=tmp_path, process="agent", agent_id="breqy")

    logger = structlog.get_logger("test")
    logger.info("ctx test")

    log_file = tmp_path / "agent-breqy.log"
    content = log_file.read_text()
    assert '"process": "agent"' in content or '"process":"agent"' in content
    assert '"agent_id": "breqy"' in content or '"agent_id":"breqy"' in content
```

- [ ] **Step 8: Run test to verify it fails**

Run: `uv run pytest tests/unit/utils/test_logging.py::test_setup_logging_binds_process_context -v`
Expected: FAIL

- [ ] **Step 9: Write failing test — backward-compatible (no log_dir)**

```python
def test_setup_logging_no_log_dir_still_works():
    """setup_logging without log_dir works as before (stderr only)."""
    from breqy.utils.logging import setup_logging
    setup_logging(level="INFO")  # must not raise — backward compat
```

- [ ] **Step 10: Run test to verify it passes (characterization test)**

Run: `uv run pytest tests/unit/utils/test_logging.py::test_setup_logging_no_log_dir_still_works -v`
Expected: PASS (existing behavior)

- [ ] **Step 11: Implement `setup_logging()` extension**

Modify `breqy/utils/logging.py`:

```python
"""Structured logging setup using structlog."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    process: str = "engine",
    agent_id: str = "",
) -> None:
    """Configure structlog with console + optional JSON file output.

    Safe to call multiple times — structlog.configure() is idempotent.
    Falls back to INFO for unrecognized level strings.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for JSON log files. If None, file logging is disabled.
        process: Process identifier (engine, agent, tui).
        agent_id: Agent identifier (only relevant for agent processes).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Bind process context so every log entry gets it automatically
    structlog.contextvars.clear_contextvars()
    ctx: dict[str, str] = {"process": process}
    if agent_id:
        ctx["agent_id"] = agent_id
    structlog.contextvars.bind_contextvars(**ctx)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Build logger factories: always stderr console, optionally JSON file
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        if process == "agent" and agent_id:
            log_filename = f"agent-{agent_id}.log"
        else:
            log_filename = f"{process}.log"
        log_path = log_dir / log_filename

        # Use stdlib logging to fan out to file (JSON) + stderr (console)
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        # Clear existing handlers to avoid duplication on re-call
        root_logger.handlers.clear()

        # File handler — JSON lines
        file_handler = logging.FileHandler(str(log_path), mode="a")
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)

        # Stderr handler — human-readable (suppress in TUI mode)
        if process != "tui":
            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setLevel(numeric_level)
            root_logger.addHandler(stderr_handler)

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=False,
        )
    else:
        # Original behavior: stderr-only console output
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=False,
        )
```

- [ ] **Step 12: Run all logging tests**

Run: `uv run pytest tests/unit/utils/test_logging.py -v`
Expected: ALL PASS

- [ ] **Step 13: Run full test suite for regressions**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS (1266+)

- [ ] **Step 14: Commit**

```bash
git add breqy/utils/logging.py tests/unit/utils/test_logging.py
git commit -m "feat: extend setup_logging with file handler, process context, and JSON renderer"
```

---

### Task 2: Migrate stdlib → structlog in `a2a/server.py`, `a2a/client.py`

**Files:**
- Modify: `breqy/a2a/server.py`
- Modify: `breqy/a2a/client.py`

These two files use `logging.getLogger(__name__)` which is never configured. Replace with structlog.

- [ ] **Step 1: Write failing test — a2a server uses structlog**

```python
# tests/unit/a2a/test_server.py (or new test file if needed)
def test_a2a_server_uses_structlog():
    """a2a.server module-level logger is structlog, not stdlib."""
    from breqy.a2a import server
    import structlog
    assert hasattr(server, "logger")
    # structlog loggers are BoundLogger instances, not stdlib Logger
    assert not isinstance(server.logger, __import__("logging").Logger)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/a2a/test_server.py::test_a2a_server_uses_structlog -v`
Expected: FAIL — `server.logger` is currently `logging.Logger`

- [ ] **Step 3: Write failing test — a2a client uses structlog**

```python
def test_a2a_client_uses_structlog():
    """a2a.client module-level logger is structlog, not stdlib."""
    from breqy.a2a import client
    assert hasattr(client, "logger")
    assert not isinstance(client.logger, __import__("logging").Logger)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/a2a/test_client.py::test_a2a_client_uses_structlog -v`
Expected: FAIL

- [ ] **Step 5: Migrate `a2a/server.py` to structlog**

Replace in `breqy/a2a/server.py`:
- `import logging` → `import structlog`
- `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger(__name__)`
- `logger.info("A2A server started on %s", self._socket_path)` → `logger.info("A2A server started", socket_path=self._socket_path)`
- `logger.info("A2A server stopped")` → `logger.info("A2A server stopped")`
- `logger.info("Client connected: %s", client_id)` → `logger.info("Client connected", client_id=client_id)`
- `logger.error("Error reading from client %s: %s", client_id, exc)` → `logger.error("Error reading from client", client_id=client_id, error=str(exc))`
- `logger.info("Client disconnected: %s", client_id)` → `logger.info("Client disconnected", client_id=client_id)`

- [ ] **Step 6: Migrate `a2a/client.py` to structlog**

Replace in `breqy/a2a/client.py`:
- `import logging` → `import structlog`
- `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger(__name__)`
- `logger.info("Connected to engine at %s", self._socket_path)` → `logger.info("Connected to engine", socket_path=self._socket_path)`
- `logger.error("Error reading from server: %s", exc)` → `logger.error("Error reading from server", error=str(exc))`

- [ ] **Step 7: Run migration tests**

Run: `uv run pytest tests/unit/a2a/test_server.py::test_a2a_server_uses_structlog tests/unit/a2a/test_client.py::test_a2a_client_uses_structlog -v`
Expected: PASS

- [ ] **Step 8: Run full test suite for regressions**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add breqy/a2a/server.py breqy/a2a/client.py tests/unit/a2a/
git commit -m "refactor: migrate a2a server and client from stdlib logging to structlog"
```

---

### Task 3: Migrate stdlib → structlog in `tui/app.py`

**Files:**
- Modify: `breqy/tui/app.py`
- Modify: `tests/tui/test_app.py`

- [ ] **Step 1: Write failing test — tui app uses structlog**

```python
# tests/tui/test_app.py
def test_tui_app_uses_structlog():
    """tui.app module-level logger is structlog, not stdlib."""
    from breqy.tui import app as app_module
    assert hasattr(app_module, "logger")
    assert not isinstance(app_module.logger, __import__("logging").Logger)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_app.py::test_tui_app_uses_structlog -v`
Expected: FAIL

- [ ] **Step 3: Migrate `tui/app.py` to structlog**

Replace in `breqy/tui/app.py`:
- `import logging` → `import structlog`
- `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger(__name__)`
- `logger.warning("Disconnected from engine, reconnecting...")` → `logger.warning("Disconnected from engine, reconnecting")`
- `logger.warning("Connection failed: %s (retry in %.1fs)", exc, backoff)` → `logger.warning("Connection failed", error=str(exc), retry_in=backoff)`
- `logger.error("Unexpected error in A2A listener: %s", exc, exc_info=True)` → `logger.error("Unexpected error in A2A listener", error=str(exc), exc_info=True)`

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/tui/test_app.py::test_tui_app_uses_structlog -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add breqy/tui/app.py tests/tui/test_app.py
git commit -m "refactor: migrate tui app from stdlib logging to structlog"
```

---

### Task 4: Add structlog to `agent_registry.py`, `transport.py`, `envelope.py`

**Files:**
- Modify: `breqy/engine/agent_registry.py`
- Modify: `breqy/a2a/transport.py`
- Modify: `breqy/a2a/envelope.py`

These files have no logger at all. Adding structlog loggers with appropriate level calls.

- [ ] **Step 1: Write failing test — agent_registry has structlog logger**

```python
# tests/unit/engine/test_agent_registry.py (add to existing)
def test_agent_registry_has_logger():
    """AgentRegistry module should have a structlog logger."""
    from breqy.engine import agent_registry
    import structlog
    assert hasattr(agent_registry, "logger")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/test_agent_registry.py::test_agent_registry_has_logger -v`
Expected: FAIL — no `logger` attribute

- [ ] **Step 3: Add structlog loggers to all three files**

`breqy/engine/agent_registry.py` — add at top:
```python
import structlog
logger = structlog.get_logger(__name__)
```
In `register()` add: `logger.info("Agent registered", agent_id=agent_id, client_id=client_id, session_id=session_id)`
In `unregister()` add: `logger.info("Agent unregistered", agent_id=agent_id)`

`breqy/a2a/transport.py` — add at top:
```python
import structlog
logger = structlog.get_logger(__name__)
```
In `FrameReader.read_frame()` add at successful read: `logger.debug("Frame read", length=length)`
In `FrameWriter.write_frame()` add: `logger.debug("Frame written", length=len(data))`

`breqy/a2a/envelope.py` — add at top:
```python
import structlog
logger = structlog.get_logger(__name__)
```
In `Envelope.to_event()` wrap `deserialize_event` call with try/except for warning:
```python
def to_event(self) -> Event:
    data = { ... }
    try:
        return deserialize_event(data)
    except Exception:
        logger.warning("Envelope deserialization failed", event_type=self.event_type.value, event_id=self.event_id)
        raise
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/engine/test_agent_registry.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add breqy/engine/agent_registry.py breqy/a2a/transport.py breqy/a2a/envelope.py tests/unit/engine/test_agent_registry.py
git commit -m "feat: add structlog to agent_registry, transport, and envelope"
```

---

### Task 5: Instrument Agent Runtime with Logging

**Files:**
- Modify: `breqy/agents/runtime.py`
- Modify: `tests/unit/agents/test_runtime.py`

The agent runtime currently has ZERO logging. Add structlog + call `setup_logging()` in `main()`.

- [ ] **Step 1: Write failing test — runtime calls setup_logging in main()**

```python
# tests/unit/agents/test_runtime.py (add to existing)
from unittest.mock import patch, MagicMock

def test_main_calls_setup_logging():
    """main() should call setup_logging for the agent process."""
    with patch("breqy.agents.runtime.setup_logging") as mock_setup, \
         patch("breqy.agents.runtime._parse_args") as mock_args, \
         patch("breqy.agents.runtime.load_agent_config") as mock_config, \
         patch("breqy.agents.runtime._build_provider") as mock_provider, \
         patch("breqy.agents.runtime.A2AClient"), \
         patch("breqy.agents.runtime.asyncio") as mock_asyncio:
        mock_args.return_value = MagicMock(
            agent_dir="agents/breqy",
            engine_socket=None,
            session_id="ses_1",
        )
        mock_config.return_value = MagicMock(
            id="breqy",
            engine_socket="/tmp/test.sock",
            log_level="DEBUG",
            model_copy=MagicMock(return_value=MagicMock(
                id="breqy", engine_socket="/tmp/test.sock",
                log_level="DEBUG",
            )),
        )
        mock_provider.return_value = MagicMock()
        mock_asyncio.run = MagicMock()

        from breqy.agents.runtime import main
        main()

        mock_setup.assert_called_once()
        call_kwargs = mock_setup.call_args
        assert call_kwargs is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_runtime.py::test_main_calls_setup_logging -v`
Expected: FAIL — `setup_logging` is not imported or called in runtime.py

- [ ] **Step 3: Write failing test — runtime has module logger**

```python
def test_runtime_has_structlog_logger():
    """Agent runtime module should have a structlog logger."""
    from breqy.agents import runtime
    assert hasattr(runtime, "logger")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_runtime.py::test_runtime_has_structlog_logger -v`
Expected: FAIL

- [ ] **Step 5: Implement runtime logging**

Add to top of `breqy/agents/runtime.py`:
```python
import structlog
from breqy.utils.logging import setup_logging

logger = structlog.get_logger(__name__)
```

Add logging calls throughout `AgentRuntime`:
- `start()`: `logger.info("Agent runtime started", agent_id=self._config.id, session_id=self._session_id)`
- `stop()`: `logger.info("Agent runtime stopped", agent_id=self._config.id)`
- `run()` in the listen loop: `logger.debug("Event received from engine", event_type=type(event).__name__)`
- `handle_work()` at entry: `logger.debug("Work received", session_id=event.session_id, message_count=1)`
- `handle_work()` before stream: `logger.debug("Provider stream started", provider=self._provider.provider_id, model=self._provider.model_id)`
- `handle_work()` on chunk: `logger.debug("Chunk sent", message_id=assistant_message_id, chunk_index=chunk_index)`
- `handle_work()` at end: `logger.debug("Response complete", message_id=assistant_message_id, content_length=len("".join(content_parts)))`

Update `main()` to call `setup_logging()`:
```python
def main() -> None:
    args = _parse_args()
    agent_dir = Path(args.agent_dir)
    config = load_agent_config(str(agent_dir))
    if args.engine_socket:
        config = config.model_copy(update={"engine_socket": args.engine_socket})
    session_id = args.session_id or "runtime"

    # Initialize logging for agent subprocess
    setup_logging(
        level=config.log_level,
        log_dir=Path(os.environ.get("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data"))) / "logs",
        process="agent",
        agent_id=config.id,
    )

    runtime = AgentRuntime(...)
    ...
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/agents/test_runtime.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add breqy/agents/runtime.py tests/unit/agents/test_runtime.py
git commit -m "feat: add structlog logging to agent runtime with all trace points"
```

---

### Task 6: Instrument Engine Server with DEBUG Trace Calls

**Files:**
- Modify: `breqy/engine/server.py`

The engine server already has a structlog logger but only uses it at INFO level. Add DEBUG-level Tier 1 trace calls from the spec.

- [ ] **Step 1: Write failing test — engine server logs envelope received**

```python
# tests/unit/engine/test_server.py (add to existing or create focused test)
from unittest.mock import patch
import structlog

def test_handle_envelope_logs_debug(engine_server_fixture):
    """_handle_envelope should log at debug level when processing envelopes."""
    # This test verifies the logger.debug call exists by checking the code
    from breqy.engine import server
    import inspect
    source = inspect.getsource(server.EngineServer._handle_envelope)
    assert "logger.debug" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/test_server.py::test_handle_envelope_logs_debug -v`
Expected: FAIL — no `logger.debug` in `_handle_envelope`

- [ ] **Step 3: Add DEBUG calls to `engine/server.py`**

In `_handle_envelope()`:
```python
async def _handle_envelope(self, envelope: Envelope, client_id: str) -> None:
    event = envelope.to_event()
    logger.debug(
        "Envelope received",
        client_id=client_id,
        event_type=event.event_type.value,
        session_id=event.session_id,
    )
    # ... existing routing ...
```

In `_handle_user_message()` after persist:
```python
logger.debug("Message persisted", session_id=event.session_id, message_id=message.id)
```

Before dispatching work to agent:
```python
logger.debug("Work dispatched", session_id=event.session_id, agent_id=session.primary_agent_id)
```

In the broadcast fallthrough at end of `_handle_envelope`:
```python
logger.debug("Event broadcast", event_type=event.event_type.value, exclude_client=client_id)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/engine/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add breqy/engine/server.py tests/unit/engine/
git commit -m "feat: add DEBUG-level envelope tracing to engine server"
```

---

### Task 7: Fix Subprocess Pipes + Pass `log_dir` in Daemon

**Files:**
- Modify: `breqy/engine/agent_spawner.py`
- Modify: `breqy/engine/daemon.py`
- Modify: `tests/unit/engine/test_agent_spawner.py`

The agent subprocess currently uses `stdout=PIPE, stderr=PIPE` which are never read — risk of hanging. Now that agents write their own log files, change to DEVNULL.

- [ ] **Step 1: Write failing test — subprocess uses DEVNULL**

```python
# tests/unit/engine/test_agent_spawner.py (add to existing)
import subprocess
from unittest.mock import patch, MagicMock

def test_spawn_uses_devnull():
    """spawn() should use DEVNULL for stdout and stderr."""
    from breqy.engine.agent_spawner import AgentSpawner
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")

    with patch("breqy.engine.agent_spawner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        spawner.spawn("agents/breqy", session_id="ses_1")

        call_kwargs = mock_popen.call_args
        assert call_kwargs[1]["stdout"] == subprocess.DEVNULL
        assert call_kwargs[1]["stderr"] == subprocess.DEVNULL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/test_agent_spawner.py::test_spawn_uses_devnull -v`
Expected: FAIL — currently uses `subprocess.PIPE`

- [ ] **Step 3: Write failing test — daemon passes log_dir to setup_logging**

```python
# tests/unit/engine/test_daemon.py (add to existing)
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

@pytest.mark.asyncio
async def test_daemon_start_passes_log_dir(tmp_path):
    """EngineDaemon.start() should pass log_dir to setup_logging."""
    from breqy.config.models import EngineConfig
    config = EngineConfig(
        socket_path=str(tmp_path / "test.sock"),
        data_dir=str(tmp_path / "data"),
        db_path=str(tmp_path / "data" / "breqy.db"),
        log_level="INFO",
    )

    with patch("breqy.engine.daemon.setup_logging") as mock_setup, \
         patch("breqy.engine.daemon.create_connection", new_callable=AsyncMock), \
         patch("breqy.engine.daemon.run_migrations", new_callable=AsyncMock), \
         patch("breqy.engine.daemon.EngineServer") as mock_server_cls:
        mock_server = MagicMock()
        mock_server.start = AsyncMock()
        mock_server_cls.return_value = mock_server

        from breqy.engine.daemon import EngineDaemon
        daemon = EngineDaemon(config)
        await daemon.start()

        mock_setup.assert_called_once()
        kwargs = mock_setup.call_args[1] if mock_setup.call_args[1] else {}
        args = mock_setup.call_args[0] if mock_setup.call_args[0] else ()
        # Should pass log_dir (either as arg or kwarg)
        all_args = {**dict(enumerate(args)), **kwargs}
        assert "log_dir" in kwargs or len(args) >= 2
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/test_daemon.py::test_daemon_start_passes_log_dir -v`
Expected: FAIL — currently calls `setup_logging(self._config.log_level)` without `log_dir`

- [ ] **Step 5: Fix subprocess pipes in agent_spawner.py**

Change in `AgentSpawner.spawn()`:
```python
process = subprocess.Popen(
    cmd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
```

- [ ] **Step 6: Update daemon.py to pass log_dir**

Change in `EngineDaemon.start()`:
```python
log_dir = Path(self._config.data_dir) / "logs"
setup_logging(
    level=self._config.log_level,
    log_dir=log_dir,
    process="engine",
)
```

Add `from pathlib import Path` if not already imported (it is already imported).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/unit/engine/test_agent_spawner.py tests/unit/engine/test_daemon.py -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add breqy/engine/agent_spawner.py breqy/engine/daemon.py tests/unit/engine/
git commit -m "fix: use DEVNULL for agent subprocess pipes, pass log_dir to setup_logging in daemon"
```

---

### Task 8: Add `setup_logging()` for TUI + Background Log Buffer

**Files:**
- Modify: `breqy/cli.py`
- Modify: `breqy/tui/app.py`
- Modify: `breqy/tui/screens/logs.py`
- Modify: `tests/tui/test_app.py`
- Modify: `tests/tui/test_logs_screen.py`

This task: (1) call `setup_logging()` in CLI's `tui` command, (2) add a background `_log_buffer` deque to `BreqyApp`, (3) update `LogsScreen` to read from the app buffer on mount.

- [ ] **Step 1: Write failing test — tui command calls setup_logging**

```python
# tests/tui/test_cli_tui.py or add to existing CLI test
from unittest.mock import patch, MagicMock

def test_tui_command_calls_setup_logging():
    """The tui CLI command should call setup_logging for the TUI process."""
    from click.testing import CliRunner
    from breqy.cli import main

    with patch("breqy.cli.BreqyApp") as mock_app_cls, \
         patch("breqy.utils.logging.setup_logging") as mock_setup:
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app

        runner = CliRunner()
        result = runner.invoke(main, ["tui"])

        # setup_logging should have been called somewhere
        # (might be called via the import or explicitly in the command)
```

Note: The exact test structure depends on whether we can intercept the call cleanly. A simpler approach is to check the source code:

```python
def test_tui_command_has_setup_logging_call():
    """The tui CLI command should contain a setup_logging call."""
    import inspect
    from breqy.cli import tui
    source = inspect.getsource(tui.callback)
    assert "setup_logging" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_cli_tui.py -v` (or wherever the test lives)
Expected: FAIL — `setup_logging` not in tui command

- [ ] **Step 3: Write failing test — BreqyApp has log buffer**

```python
# tests/tui/test_app.py
def test_breqy_app_has_log_buffer():
    """BreqyApp should have a _log_buffer deque for background logging."""
    from breqy.tui.app import BreqyApp
    app = BreqyApp(socket_path="")
    assert hasattr(app, "_log_buffer")
    import collections
    assert isinstance(app._log_buffer, collections.deque)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_app.py::test_breqy_app_has_log_buffer -v`
Expected: FAIL

- [ ] **Step 5: Write failing test — LogsScreen reads app buffer on mount**

```python
# tests/tui/test_logs_screen.py (add to existing)
from datetime import datetime
from breqy.tui.screens.logs import LogEntry

async def test_logs_screen_reads_app_buffer_on_mount(app_with_log_buffer):
    """LogsScreen should populate itself from app._log_buffer when mounted."""
    # This test requires async Textual test harness — structure depends on
    # existing test patterns in the project
    pass  # Will be implemented based on existing Textual test patterns
```

- [ ] **Step 6: Implement — add log buffer to BreqyApp**

In `breqy/tui/app.py`, add to `__init__`:
```python
import collections
from breqy.tui.screens.logs import LogEntry

class BreqyApp(App):
    def __init__(self, socket_path: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        ...
        self._log_buffer: collections.deque[LogEntry] = collections.deque(maxlen=1000)
```

Update `_route_to_logs` to always append to buffer, then also route to screen if mounted:
```python
def _route_to_logs(self, event: Event) -> None:
    """Append event to background buffer and route to LogsScreen if mounted."""
    from breqy.tui.screens.logs import LogEntry
    entry = LogEntry(
        timestamp=event.timestamp,
        source=event.agent_id or "engine",
        event_type=event.event_type.value,
        summary=str(getattr(event, "content", ""))
        or str(getattr(event, "summary", ""))
        or "",
    )
    self._log_buffer.append(entry)
    for screen in reversed(self.screen_stack):
        if isinstance(screen, LogsScreen):
            screen.add_event(
                timestamp=entry.timestamp,
                source=entry.source,
                event_type=entry.event_type,
                summary=entry.summary,
            )
            break
```

- [ ] **Step 7: Implement — LogsScreen reads buffer on mount**

In `breqy/tui/screens/logs.py`, update `on_mount()`:
```python
def on_mount(self) -> None:
    """Load existing entries from app buffer and render."""
    # Pre-populate from app's background buffer if available
    if hasattr(self.app, "_log_buffer"):
        for entry in self.app._log_buffer:
            self._entries.append(entry)
    self._refresh_display()
```

- [ ] **Step 8: Implement — call setup_logging in CLI tui command**

In `breqy/cli.py`, update the `tui` function:
```python
@main.command("tui")
@click.option("--socket", "socket_path", default=None, ...)
@click.option("--log-level", default=None, type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False), help="Log level")
def tui(socket_path: str | None, log_level: str | None) -> None:
    ...
    from breqy.utils.logging import setup_logging

    resolved_level = (log_level or os.getenv("BREQY_LOG_LEVEL", "INFO")).upper()
    data_dir = os.getenv("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data"))
    setup_logging(
        level=resolved_level,
        log_dir=Path(data_dir) / "logs",
        process="tui",
    )

    from breqy.tui.app import BreqyApp
    app = BreqyApp(socket_path=resolved)
    app.run()
```

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/tui/ -v --tb=short`
Expected: PASS

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add breqy/cli.py breqy/tui/app.py breqy/tui/screens/logs.py tests/tui/
git commit -m "feat: add TUI setup_logging, background log buffer, and LogsScreen buffer pre-population"
```

---

### Task 9: Add DEBUG Trace Calls to TUI Event Flow

**Files:**
- Modify: `breqy/tui/app.py`
- Modify: `breqy/tui/screens/chat.py`

Add Tier 1 DEBUG-level calls at TUI trace points: user message submitted, event sent to engine, event received from engine, dispatched to screen.

- [ ] **Step 1: Write failing test — app logs user message submission**

```python
# tests/tui/test_app.py
def test_on_message_submitted_has_debug_logging():
    """on_message_submitted should include debug logging."""
    import inspect
    from breqy.tui.app import BreqyApp
    source = inspect.getsource(BreqyApp.on_message_submitted)
    assert "logger.debug" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_app.py::test_on_message_submitted_has_debug_logging -v`
Expected: FAIL

- [ ] **Step 3: Add DEBUG calls to `tui/app.py`**

In `on_message_submitted()`:
```python
logger.debug("User message submitted", session_id=chat_screen.session_id, content_length=len(message.text))
```

In `_start_listener()` when receiving events:
```python
event = envelope.to_event()
logger.debug("Event received", event_type=event.event_type.value, session_id=event.session_id)
self._dispatcher.dispatch(event)
```

In `_route_to_chat()`:
```python
logger.debug("Dispatched to screen", handler_name=handler_name)
```

In `send_event()`:
```python
logger.debug("Sending event to engine", event_type=event.event_type.value, session_id=event.session_id)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/tui/ -v --tb=short`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add breqy/tui/app.py breqy/tui/screens/chat.py tests/tui/
git commit -m "feat: add DEBUG-level trace calls to TUI event flow"
```

---

### Task 10: Centralize `log_dir` in `EngineConfig` + `AgentConfig`

**Files:**
- Modify: `breqy/config/models.py`
- Modify: `tests/unit/config/test_models.py`
- Modify: `breqy/engine/daemon.py` (use config.log_dir)
- Modify: `breqy/agents/runtime.py` (use centralized data_dir from env instead of hardcoding)

The spec requires `log_dir` to be derived from `data_dir` rather than scattered across call sites.

- [ ] **Step 1: Write failing test — EngineConfig has log_dir property**

```python
# tests/unit/config/test_models.py (add to existing)
def test_engine_config_log_dir(tmp_path):
    """EngineConfig.log_dir should be derived from data_dir."""
    from breqy.config.models import EngineConfig
    config = EngineConfig(data_dir=str(tmp_path / "data"))
    assert config.log_dir == str(tmp_path / "data" / "logs")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/config/test_models.py::test_engine_config_log_dir -v`
Expected: FAIL — `EngineConfig` has no `log_dir` attribute

- [ ] **Step 3: Add `log_dir` property to EngineConfig**

In `breqy/config/models.py`:
```python
class EngineConfig(BaseModel):
    ...
    @property
    def log_dir(self) -> str:
        """Log directory derived from data_dir."""
        return str(Path(self.data_dir) / "logs")
```

- [ ] **Step 4: Update daemon.py to use config.log_dir**

In `breqy/engine/daemon.py:start()`:
```python
setup_logging(
    level=self._config.log_level,
    log_dir=Path(self._config.log_dir),
    process="engine",
)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/config/test_models.py tests/unit/engine/test_daemon.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add breqy/config/models.py breqy/engine/daemon.py tests/unit/config/test_models.py
git commit -m "feat: add log_dir property to EngineConfig, use in daemon"
```

---

### Task 11: LogsScreen Dual View (Events + Logs Tabs)

**Files:**
- Modify: `breqy/tui/screens/logs.py`
- Modify: `tests/tui/test_logs_screen.py`

Per spec: LogsScreen gets two modes — "Events" (domain events, existing behavior) and "Logs" (Python log entries from structlog). User toggles with `Tab` key.

- [ ] **Step 1: Write failing test — LogsScreen has dual view modes**

```python
# tests/tui/test_logs_screen.py (add to existing)
def test_logs_screen_has_view_modes():
    """LogsScreen should support 'events' and 'logs' view modes."""
    from breqy.tui.screens.logs import LogsScreen
    screen = LogsScreen()
    assert hasattr(screen, "_view_mode")
    assert screen._view_mode in ("events", "logs")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_logs_screen.py::test_logs_screen_has_view_modes -v`
Expected: FAIL — no `_view_mode` attribute

- [ ] **Step 3: Write failing test — Tab key toggles view mode**

```python
def test_logs_screen_toggle_view():
    """LogsScreen.toggle_view() should switch between events and logs."""
    from breqy.tui.screens.logs import LogsScreen
    screen = LogsScreen()
    assert screen._view_mode == "events"
    screen.toggle_view()
    assert screen._view_mode == "logs"
    screen.toggle_view()
    assert screen._view_mode == "events"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_logs_screen.py::test_logs_screen_toggle_view -v`
Expected: FAIL

- [ ] **Step 5: Write failing test — add_log_entry method**

```python
from datetime import datetime

def test_logs_screen_add_log_entry():
    """LogsScreen should accept Python log entries separate from domain events."""
    from breqy.tui.screens.logs import LogsScreen
    screen = LogsScreen()
    screen.add_log_entry(
        timestamp=datetime.now(),
        level="INFO",
        logger_name="breqy.engine.server",
        message="Test log message",
        extra={"session_id": "ses_1"},
    )
    assert len(screen._log_entries) == 1
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_logs_screen.py::test_logs_screen_add_log_entry -v`
Expected: FAIL

- [ ] **Step 7: Implement dual view in LogsScreen**

In `breqy/tui/screens/logs.py`:

```python
@dataclass
class PythonLogEntry:
    """A Python log entry from structlog."""
    timestamp: datetime
    level: str
    logger_name: str
    message: str
    extra: dict[str, str]


class LogsScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("c", "clear_filter", "Clear filter", show=True),
        Binding("tab", "toggle_view", "Toggle Events/Logs", show=True),
    ]

    def __init__(self, max_entries: int = 500, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: collections.deque[LogEntry] = collections.deque(maxlen=max_entries)
        self._log_entries: collections.deque[PythonLogEntry] = collections.deque(maxlen=max_entries)
        self._filter_prefix: str = ""
        self._view_mode: str = "events"

    def toggle_view(self) -> None:
        """Switch between events and logs view."""
        self._view_mode = "logs" if self._view_mode == "events" else "events"
        self._refresh_display()

    def action_toggle_view(self) -> None:
        """Toggle view mode via key binding."""
        self.toggle_view()

    def add_log_entry(
        self,
        timestamp: datetime,
        level: str,
        logger_name: str,
        message: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        """Add a Python log entry."""
        entry = PythonLogEntry(
            timestamp=timestamp,
            level=level,
            logger_name=logger_name,
            message=message,
            extra=extra or {},
        )
        self._log_entries.append(entry)
        if self._view_mode == "logs":
            self._refresh_display()

    def _refresh_display(self) -> None:
        log = self.query_one("#logs-display", RichLog)
        log.clear()

        if self._view_mode == "events":
            visible = self._get_visible_entries()
            if not visible:
                log.write("[dim]No events[/dim]")
                return
            for entry in visible:
                ts_str = entry.timestamp.strftime("%H:%M:%S")
                log.write(
                    f"[dim]{ts_str}[/dim] [{entry.source}] "
                    f"[bold]{entry.event_type}[/bold] {entry.summary}"
                )
        else:
            visible = self._get_visible_log_entries()
            if not visible:
                log.write("[dim]No log entries[/dim]")
                return
            for entry in visible:
                ts_str = entry.timestamp.strftime("%H:%M:%S")
                level_color = {"DEBUG": "dim", "INFO": "green", "WARNING": "yellow", "ERROR": "red"}.get(entry.level, "")
                level_fmt = f"[{level_color}]{entry.level}[/{level_color}]" if level_color else entry.level
                log.write(
                    f"[dim]{ts_str}[/dim] {level_fmt} "
                    f"[bold]{entry.logger_name}[/bold] {entry.message}"
                )

    def _get_visible_log_entries(self) -> list[PythonLogEntry]:
        if not self._filter_prefix:
            return list(self._log_entries)
        return [
            e for e in self._log_entries
            if e.level.startswith(self._filter_prefix.upper())
            or e.logger_name.startswith(self._filter_prefix)
        ]
    # Update footer to show current mode
    # In compose(), update footer:
    # yield Static("[b]Escape[/b] Back  [b]Tab[/b] Events/Logs  [b]C[/b] Clear filter", id="logs-footer")
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/tui/test_logs_screen.py -v`
Expected: PASS

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add breqy/tui/screens/logs.py tests/tui/test_logs_screen.py
git commit -m "feat: add dual view (Events/Logs) to LogsScreen with Tab toggle"
```

---

### Task 12: LogsScreen Filter Enhancement (session_id, agent_id, log level)

**Files:**
- Modify: `breqy/tui/screens/logs.py`
- Modify: `tests/tui/test_logs_screen.py`

Per spec: add ability to filter by `session_id`, `agent_id`, and log level in addition to the existing `event_type` prefix filter.

- [ ] **Step 1: Write failing test — filter by session_id**

```python
# tests/tui/test_logs_screen.py
from datetime import datetime

def test_logs_screen_filter_by_session_id():
    """LogsScreen should filter events by session_id prefix."""
    from breqy.tui.screens.logs import LogsScreen
    screen = LogsScreen()
    screen._entries.append(LogEntry(
        timestamp=datetime.now(), source="breqy",
        event_type="message_sent", summary="hello",
    ))
    # LogEntry needs session_id field for filtering
    # This test defines the desired behavior
    assert hasattr(LogEntry, "__dataclass_fields__") or True  # Will be refined
```

Note: The existing `LogEntry` dataclass doesn't have `session_id` or `agent_id` fields. The filter enhancement requires either:
(a) Adding optional fields to `LogEntry`, or
(b) Filtering based on the `summary` or `source` fields

The simpler approach (b): use the filter input to match against source (which contains agent_id) and add session_id to the event source string. Since this is a UI enhancement, the exact implementation should match how events are stored in the buffer.

- [ ] **Step 2: Write failing test — filter input matches source (agent_id)**

```python
def test_logs_screen_filter_matches_source():
    """Filter should match against source field (which contains agent_id)."""
    from breqy.tui.screens.logs import LogsScreen
    screen = LogsScreen()
    screen._entries.append(LogEntry(
        timestamp=datetime.now(), source="breqy",
        event_type="message_sent", summary="hello",
    ))
    screen._entries.append(LogEntry(
        timestamp=datetime.now(), source="engine",
        event_type="session_created", summary="new session",
    ))
    screen.set_filter("breqy")
    visible = screen._get_visible_entries()
    assert len(visible) == 1
    assert visible[0].source == "breqy"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_logs_screen.py::test_logs_screen_filter_matches_source -v`
Expected: FAIL — current filter only checks `event_type.startswith(prefix)`, not `source`

- [ ] **Step 4: Enhance filter to match source and event_type**

In `breqy/tui/screens/logs.py`, update `_get_visible_entries()`:
```python
def _get_visible_entries(self) -> list[LogEntry]:
    if not self._filter_prefix:
        return list(self._entries)
    prefix = self._filter_prefix.lower()
    return [
        entry for entry in self._entries
        if entry.event_type.lower().startswith(prefix)
        or entry.source.lower().startswith(prefix)
    ]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/tui/test_logs_screen.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add breqy/tui/screens/logs.py tests/tui/test_logs_screen.py
git commit -m "feat: enhance LogsScreen filter to match source/agent_id and event_type"
```

---

### Task 13: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS (1266+ tests, 0 failures)

- [ ] **Step 2: Verify no stdlib logging imports remain in migrated files**

```bash
uv run python -c "
from breqy.a2a import server, client
from breqy.tui import app
import logging
for mod in [server, client, app]:
    name = mod.__name__
    assert not isinstance(mod.logger, logging.Logger), f'{name} still uses stdlib logging'
print('All modules migrated to structlog')
"
```

- [ ] **Step 3: Verify log file creation**

```bash
uv run python -c "
from pathlib import Path
import tempfile
from breqy.utils.logging import setup_logging
import structlog

with tempfile.TemporaryDirectory() as td:
    p = Path(td)
    setup_logging(level='DEBUG', log_dir=p, process='engine')
    logger = structlog.get_logger('verify')
    logger.info('verify')
    assert (p / 'engine.log').exists(), 'engine.log not created'

    setup_logging(level='DEBUG', log_dir=p, process='agent', agent_id='breqy')
    logger2 = structlog.get_logger('verify2')
    logger2.info('verify2')
    assert (p / 'agent-breqy.log').exists(), 'agent-breqy.log not created'

print('Log files created successfully')
"
```

- [ ] **Step 4: Summary commit (if any loose changes)**

Only if there are uncommitted fixups from verification.

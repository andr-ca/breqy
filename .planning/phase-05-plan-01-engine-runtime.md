# Phase 5 Plan 01: Engine Runtime

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Engine Runtime — the async in-process pub/sub event bus, session manager, agent registry, agent spawner, and the engine server/daemon that ties all components together.

**Architecture:** Five components in `breqy/engine/`:
- `event_bus.py` — `EventBus` (in-process typed pub/sub, already partially exists as `event_writer.py`)
- `session_manager.py` — `SessionManager` (create/resume/list/close sessions + messages)
- `agent_registry.py` — `AgentRegistry` (track connected agent IDs and PIDs)
- `agent_spawner.py` — `AgentSpawner` (spawn agent subprocesses)
- `server.py` — `EngineServer` (composites all engine components)
- `daemon.py` — `EngineDaemon` (lifecycle: start, stop, signal handling)

> **Note:** `breqy/engine/__init__.py` and `breqy/engine/event_writer.py` already exist from Phase 2.

> **IMPORTANT:** The spec doc at `docs/plans/2026-03-13-breqy-slice-1.md` has `engine/server.py` importing from `breqy.approval.service`. In this worktree, `ApprovalService` is at `breqy.policy.approval.ApprovalService` — use that import path.

> **IMPORTANT:** The spec uses `writer.enqueue(event)` but the existing `EventWriter` uses `writer.write(event)` — use `write()`.

**Tech Stack:** Python 3.12, asyncio, subprocess, structlog

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Run tests with:** `uv run pytest`

---

## Key Domain Facts (read before coding)

From existing worktree code:
- `EngineConfig` fields: `socket_path`, `data_dir`, `db_path`, `log_level`, `default_agent_id`
- `EventWriter.write(event)` — use this, not `enqueue()`
- `ApprovalService` is in `breqy.policy.approval` (not `breqy.approval.service`)
- `A2AServer(socket_path, on_envelope)` — `on_envelope` is `Callable[[Envelope, str], Coroutine]`
- `A2AServer.broadcast(envelope, exclude_client="")` — existing API
- `Session.primary_agent_id` — correct field name
- `SessionRepository.list_active()` — list active sessions
- `SessionRepository.update_status(session_id, status)` — update status
- `SessionRepository.update_timestamp(session_id)` — update updated_at
- Conftest fixtures available: `db_connection` (aiosqlite.Connection with schema), `tmp_dir` (Path), `socket_path` (Path)
- Use `structlog.get_logger(__name__)` not stdlib `logging`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `breqy/engine/event_bus.py` | Create | `EventBus` in-process async pub/sub |
| `breqy/engine/session_manager.py` | Create | `SessionManager` — create/resume/list/close |
| `breqy/engine/agent_registry.py` | Create | `AgentRegistry` — track connected agents |
| `breqy/engine/agent_spawner.py` | Create | `AgentSpawner` — subprocess management |
| `breqy/engine/server.py` | Create | `EngineServer` — composition root |
| `breqy/engine/daemon.py` | Create | `EngineDaemon` — lifecycle + signal handling |
| `tests/unit/engine/test_event_bus.py` | Create | 3 tests for EventBus |
| `tests/unit/engine/test_session_manager.py` | Create | 4 tests for SessionManager |
| `tests/unit/engine/test_agent_registry.py` | Create | 3 tests for AgentRegistry |
| `tests/unit/engine/test_agent_spawner.py` | Create | 2 tests for AgentSpawner |
| `tests/unit/engine/test_daemon.py` | Create | 2 tests for EngineDaemon |

---

## Task 1: EventBus

**Files:**
- Create: `breqy/engine/event_bus.py`
- Create: `tests/unit/engine/test_event_bus.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/engine/test_event_bus.py`:

```python
"""Tests for in-process async event bus."""
from __future__ import annotations

import asyncio

import pytest

from breqy.engine.event_bus import EventBus
from breqy.domain.events import MessageSentEvent, ToolInvocationStartedEvent
from breqy.domain.enums import EventType


@pytest.mark.asyncio
async def test_subscribe_and_receive():
    """subscribe() handler receives a matching published event."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.MESSAGE_SENT, handler)

    event = MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    )
    await bus.publish(event)
    await asyncio.sleep(0.01)

    assert len(received) == 1
    assert received[0].event_type == EventType.MESSAGE_SENT


@pytest.mark.asyncio
async def test_wildcard_subscribe():
    """subscribe_all() handler receives all event types."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe_all(handler)

    await bus.publish(MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    ))
    await bus.publish(ToolInvocationStartedEvent(
        session_id="ses_1", agent_id="breqy", invocation_id="inv_1",
        tool_name="shell", summary="ls"
    ))
    await asyncio.sleep(0.01)

    assert len(received) == 2


@pytest.mark.asyncio
async def test_unsubscribe():
    """unsubscribe() removes the handler — no events received after."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    sub_id = bus.subscribe(EventType.MESSAGE_SENT, handler)
    bus.unsubscribe(sub_id)

    await bus.publish(MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    ))
    await asyncio.sleep(0.01)

    assert len(received) == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/engine/test_event_bus.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.engine.event_bus'`

- [ ] **Step 3: Create `breqy/engine/event_bus.py`**

```python
"""In-process async event bus for the Breqy engine.

Supports typed subscriptions and wildcard (all-events) listeners.
Handlers are invoked inline (not as tasks) to keep ordering deterministic.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

import structlog

from breqy.domain.enums import EventType
from breqy.domain.events import Event
from breqy.domain.ids import generate_prefixed_id

logger = structlog.get_logger(__name__)

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus.

    Thread-safety: designed for single-thread asyncio use only.
    """

    def __init__(self) -> None:
        self._typed_handlers: dict[EventType, dict[str, EventHandler]] = {}
        self._wildcard_handlers: dict[str, EventHandler] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> str:
        """Subscribe to a specific event type. Returns subscription ID."""
        sub_id = generate_prefixed_id("sub")
        self._typed_handlers.setdefault(event_type, {})[sub_id] = handler
        return sub_id

    def subscribe_all(self, handler: EventHandler) -> str:
        """Subscribe to all event types. Returns subscription ID."""
        sub_id = generate_prefixed_id("sub")
        self._wildcard_handlers[sub_id] = handler
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscription by ID (typed or wildcard)."""
        self._wildcard_handlers.pop(sub_id, None)
        for handlers in self._typed_handlers.values():
            handlers.pop(sub_id, None)

    async def publish(self, event: Event) -> None:
        """Deliver event to all matching subscribers."""
        handlers: list[EventHandler] = list(
            self._typed_handlers.get(event.event_type, {}).values()
        )
        handlers.extend(self._wildcard_handlers.values())

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler raised",
                    event_type=str(event.event_type),
                )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/engine/test_event_bus.py -v
```
Expected: 3 passed

- [ ] **Step 5: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```

- [ ] **Step 6: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/engine/event_bus.py tests/unit/engine/test_event_bus.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(engine): add EventBus in-process async pub/sub"
```

---

## Task 2: SessionManager

**Files:**
- Create: `breqy/engine/session_manager.py`
- Create: `tests/unit/engine/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/engine/test_session_manager.py`:

```python
"""Tests for SessionManager."""
from __future__ import annotations

import pytest

from breqy.engine.session_manager import SessionManager
from breqy.domain.enums import MessageRole, SessionStatus
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository


@pytest.mark.asyncio
async def test_create_session(db_connection):
    """create_session returns an ACTIVE session with the given agent_id."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    assert session.status == SessionStatus.ACTIVE
    assert session.primary_agent_id == "breqy"

    retrieved = await manager.get_session(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id


@pytest.mark.asyncio
async def test_list_sessions(db_connection):
    """list_sessions returns all created sessions."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    await manager.create_session(agent_id="breqy")
    await manager.create_session(agent_id="breqy")

    sessions = await manager.list_sessions()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_add_message(db_connection):
    """add_message persists a message and it appears in get_messages."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    msg = await manager.add_message(session.id, MessageRole.USER, "Hello")

    assert msg.content == "Hello"
    messages = await manager.get_messages(session.id)
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_close_session(db_connection):
    """close_session sets session status to CLOSED."""
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    await manager.close_session(session.id)

    result = await manager.get_session(session.id)
    assert result is not None
    assert result.status == SessionStatus.CLOSED
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/engine/test_session_manager.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.engine.session_manager'`

- [ ] **Step 3: Create `breqy/engine/session_manager.py`**

```python
"""Session lifecycle management for the Breqy engine."""
from __future__ import annotations

import structlog

from breqy.domain.enums import MessageRole, SessionStatus
from breqy.domain.models import Message, Session
from breqy.storage.interfaces import MessageRepository, SessionRepository

logger = structlog.get_logger(__name__)


class SessionManager:
    """Creates, resumes, lists, and closes sessions."""

    def __init__(
        self,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
    ) -> None:
        self._sessions = session_repo
        self._messages = message_repo

    async def create_session(self, agent_id: str) -> Session:
        """Create and persist a new ACTIVE session."""
        session = Session(primary_agent_id=agent_id)
        await self._sessions.create(session)
        logger.info("Session created", session_id=session.id, agent_id=agent_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Return session by ID, or None if not found."""
        return await self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        """Return all active sessions."""
        return await self._sessions.list_active()

    async def close_session(self, session_id: str) -> None:
        """Mark session as CLOSED."""
        await self._sessions.update_status(session_id, SessionStatus.CLOSED)
        logger.info("Session closed", session_id=session_id)

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        agent_id: str | None = None,
    ) -> Message:
        """Persist a new message and update the session timestamp."""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            agent_id=agent_id,
        )
        await self._messages.create(message)
        await self._sessions.update_timestamp(session_id)
        return message

    async def get_messages(
        self, session_id: str, limit: int = 100
    ) -> list[Message]:
        """Return messages for a session, most recent last."""
        return await self._messages.list_by_session(session_id, limit=limit)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/engine/test_session_manager.py -v
```
Expected: 4 passed

- [ ] **Step 5: Run full suite**

```bash
uv run pytest --tb=no -q
```

- [ ] **Step 6: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/engine/session_manager.py tests/unit/engine/test_session_manager.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(engine): add SessionManager for session lifecycle"
```

---

## Task 3: AgentRegistry + AgentSpawner

**Files:**
- Create: `breqy/engine/agent_registry.py`
- Create: `breqy/engine/agent_spawner.py`
- Create: `tests/unit/engine/test_agent_registry.py`
- Create: `tests/unit/engine/test_agent_spawner.py`

- [ ] **Step 1: Write failing tests for AgentRegistry**

Create `tests/unit/engine/test_agent_registry.py`:

```python
"""Tests for AgentRegistry."""
from __future__ import annotations

from breqy.engine.agent_registry import AgentRegistry


def test_register_and_lookup():
    """register() adds an agent; get() returns it."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")

    info = registry.get("breqy")
    assert info is not None
    assert info.client_id == "cli_123"


def test_unregister():
    """unregister() removes an agent; get() returns None afterwards."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")
    registry.unregister("breqy")

    assert registry.get("breqy") is None


def test_list_agents():
    """list_agents() returns all registered agents."""
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_1")
    registry.register("docker-agent", client_id="cli_2")

    agents = registry.list_agents()
    assert len(agents) == 2
```

- [ ] **Step 2: Write failing tests for AgentSpawner**

Create `tests/unit/engine/test_agent_spawner.py`:

```python
"""Tests for AgentSpawner."""
from __future__ import annotations

import sys

from breqy.engine.agent_spawner import AgentSpawner


def test_spawner_builds_command():
    """_build_command() returns a valid python -m invocation."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    cmd = spawner._build_command("system/agents/breqy")
    assert sys.executable == cmd[0]
    assert "-m" in cmd
    assert "breqy.agents.runtime" in cmd


def test_spawner_tracks_no_processes_initially():
    """list_running() returns empty list before any spawns."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    assert spawner.list_running() == []
```

- [ ] **Step 3: Run to verify they fail**

```bash
uv run pytest tests/unit/engine/test_agent_registry.py tests/unit/engine/test_agent_spawner.py -v
```

- [ ] **Step 4: Create `breqy/engine/agent_registry.py`**

```python
"""Tracks connected agents and their A2A client IDs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentInfo:
    """Connection metadata for a registered agent."""
    agent_id: str
    client_id: str
    pid: int | None = None


class AgentRegistry:
    """Registry of currently connected agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(
        self, agent_id: str, client_id: str, pid: int | None = None
    ) -> None:
        """Register an agent connection."""
        self._agents[agent_id] = AgentInfo(
            agent_id=agent_id, client_id=client_id, pid=pid
        )

    def unregister(self, agent_id: str) -> None:
        """Remove an agent (called on disconnect)."""
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> AgentInfo | None:
        """Return agent info by agent_id, or None."""
        return self._agents.get(agent_id)

    def get_by_client_id(self, client_id: str) -> AgentInfo | None:
        """Return agent info by A2A client_id, or None."""
        for info in self._agents.values():
            if info.client_id == client_id:
                return info
        return None

    def list_agents(self) -> list[AgentInfo]:
        """Return all currently registered agents."""
        return list(self._agents.values())
```

- [ ] **Step 5: Create `breqy/engine/agent_spawner.py`**

```python
"""Agent subprocess spawner and supervisor."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SpawnedAgent:
    """Tracks a spawned agent process."""
    agent_dir: str
    process: subprocess.Popen[bytes]


class AgentSpawner:
    """Spawns and terminates agent subprocesses."""

    def __init__(self, engine_socket: str) -> None:
        self._engine_socket = engine_socket
        self._processes: dict[str, SpawnedAgent] = {}

    def spawn(self, agent_dir: str) -> int:
        """Spawn an agent process. Returns PID."""
        cmd = self._build_command(agent_dir)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._processes[agent_dir] = SpawnedAgent(
            agent_dir=agent_dir, process=process
        )
        logger.info("Agent spawned", agent_dir=agent_dir, pid=process.pid)
        return process.pid

    def kill(self, agent_dir: str) -> None:
        """Terminate an agent process."""
        spawned = self._processes.pop(agent_dir, None)
        if spawned and spawned.process.poll() is None:
            spawned.process.terminate()
            logger.info("Agent terminated", agent_dir=agent_dir)

    def kill_all(self) -> None:
        """Terminate all running agent processes."""
        for agent_dir in list(self._processes.keys()):
            self.kill(agent_dir)

    def is_running(self, agent_dir: str) -> bool:
        """Return True if the agent process is still alive."""
        spawned = self._processes.get(agent_dir)
        if spawned is None:
            return False
        return spawned.process.poll() is None

    def list_running(self) -> list[str]:
        """Return dirs of all currently-running agents."""
        return [d for d in self._processes if self.is_running(d)]

    def _build_command(self, agent_dir: str) -> list[str]:
        return [
            sys.executable, "-m", "breqy.agents.runtime",
            "--agent-dir", agent_dir,
            "--engine-socket", self._engine_socket,
        ]
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
uv run pytest tests/unit/engine/test_agent_registry.py tests/unit/engine/test_agent_spawner.py -v
```
Expected: 5 passed

- [ ] **Step 7: Run full suite**

```bash
uv run pytest --tb=no -q
```

- [ ] **Step 8: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/engine/agent_registry.py breqy/engine/agent_spawner.py \
  tests/unit/engine/test_agent_registry.py tests/unit/engine/test_agent_spawner.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(engine): add AgentRegistry and AgentSpawner"
```

---

## Task 4: EngineServer + EngineDaemon

**Files:**
- Create: `breqy/engine/server.py`
- Create: `breqy/engine/daemon.py`
- Create: `tests/unit/engine/test_daemon.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/engine/test_daemon.py`:

```python
"""Tests for EngineDaemon lifecycle."""
from __future__ import annotations

import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(tmp_dir: Path):
    """Daemon starts (is_running=True) and stops (is_running=False) cleanly."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    assert daemon.is_running

    await daemon.stop()
    assert not daemon.is_running


@pytest.mark.asyncio
async def test_daemon_creates_data_dir(tmp_dir: Path):
    """Daemon creates data_dir on startup if it doesn't exist."""
    data_dir = tmp_dir / "breqy_data"
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(data_dir / "test.db"),
        data_dir=str(data_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    assert data_dir.exists()

    await daemon.stop()
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/engine/test_daemon.py -v
```

- [ ] **Step 3: Create `breqy/engine/server.py`**

```python
"""Engine server: composites all engine components and handles A2A routing."""
from __future__ import annotations

import structlog

from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.engine.agent_registry import AgentRegistry
from breqy.engine.agent_spawner import AgentSpawner
from breqy.engine.event_bus import EventBus
from breqy.engine.event_writer import EventWriter
from breqy.engine.session_manager import SessionManager
from breqy.policy.approval import ApprovalService
from breqy.storage.interfaces import (
    ApprovalRepository,
    EventRepository,
    MessageRepository,
    SessionRepository,
    TaskRepository,
)

logger = structlog.get_logger(__name__)


class EngineServer:
    """Composes all engine subsystems and routes A2A traffic."""

    def __init__(
        self,
        socket_path: str,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        event_repo: EventRepository,
        task_repo: TaskRepository,
        approval_repo: ApprovalRepository,
    ) -> None:
        self.event_bus = EventBus()
        self.event_writer = EventWriter(event_repo)
        self.session_manager = SessionManager(session_repo, message_repo)
        self.agent_registry = AgentRegistry()
        self.agent_spawner = AgentSpawner(engine_socket=socket_path)
        self.approval_service = ApprovalService(approval_repo)
        self.a2a_server = A2AServer(
            socket_path=socket_path,
            on_envelope=self._handle_envelope,
        )

    async def start(self) -> None:
        """Start all subsystems."""
        await self.event_writer.start()
        await self.a2a_server.start()
        # Wire event writer to publish all events to bus
        self.event_bus.subscribe_all(self.event_writer.write)
        logger.info("Engine server started")

    async def stop(self) -> None:
        """Stop all subsystems cleanly."""
        self.agent_spawner.kill_all()
        await self.a2a_server.stop()
        await self.event_writer.stop()
        logger.info("Engine server stopped")

    async def _handle_envelope(self, envelope: Envelope, client_id: str) -> None:
        """Route incoming A2A envelopes from agents/TUI."""
        event = envelope.to_event()
        await self.event_bus.publish(event)
        # Broadcast to other connected clients
        await self.a2a_server.broadcast(envelope, exclude_client=client_id)
```

- [ ] **Step 4: Create `breqy/engine/daemon.py`**

```python
"""Engine daemon: lifecycle management, signal handling, entry point."""
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import structlog

from breqy.config.models import EngineConfig
from breqy.engine.server import EngineServer
from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


class EngineDaemon:
    """Top-level daemon that owns the engine lifecycle."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._server: EngineServer | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def server(self) -> EngineServer | None:
        return self._server

    async def start(self) -> None:
        """Initialize storage, build engine server, and start all components."""
        setup_logging(self._config.log_level)

        # Ensure data directory exists
        Path(self._config.data_dir).mkdir(parents=True, exist_ok=True)

        # Initialize storage layer
        conn = await create_connection(self._config.db_path)
        await run_migrations(conn)

        session_repo = SqliteSessionRepository(conn)
        message_repo = SqliteMessageRepository(conn)
        event_repo = SqliteEventRepository(conn)
        task_repo = SqliteTaskRepository(conn)
        approval_repo = SqliteApprovalRepository(conn)

        self._server = EngineServer(
            socket_path=self._config.socket_path,
            session_repo=session_repo,
            message_repo=message_repo,
            event_repo=event_repo,
            task_repo=task_repo,
            approval_repo=approval_repo,
        )
        await self._server.start()
        self._running = True
        logger.info("Engine daemon started", socket=self._config.socket_path)

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        if self._server:
            await self._server.stop()
        self._running = False
        logger.info("Engine daemon stopped")


def main() -> None:
    """Entry point for breqy-engine command."""
    from breqy.config.loader import load_engine_config

    config = load_engine_config()

    async def run() -> None:
        daemon = EngineDaemon(config)
        loop = asyncio.get_running_loop()

        def handle_signal() -> None:
            asyncio.create_task(daemon.stop())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        await daemon.start()

        while daemon.is_running:
            await asyncio.sleep(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/engine/test_daemon.py -v
```
Expected: 2 passed

- [ ] **Step 6: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```

- [ ] **Step 7: Commit**

```bash
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  add breqy/engine/server.py breqy/engine/daemon.py \
  tests/unit/engine/test_daemon.py
git -C /home/andrey/projects/breqy/.worktrees/exp-full-build \
  commit -m "feat(engine): add EngineServer composition root and EngineDaemon lifecycle"
```

---

## Final Verification

```bash
uv run pytest tests/unit/engine/ -v
```
Expected: 14 tests pass (3 event_bus + 4 session_manager + 3 agent_registry + 2 agent_spawner + 2 daemon), full suite green.

### Success Criteria

Phase 5 requirements from ROADMAP.md:
1. ✅ `EventBus` delivers typed events to subscribers; unsubscribed handler doesn't receive events
2. ✅ `SessionManager` creates/resumes/lists sessions; `close_session` marks CLOSED
3. ✅ `AgentRegistry` tracks connected agents by agent_id; unregister removes them
4. ✅ `AgentSpawner` builds correct python -m command; tracks processes
5. ✅ `EngineDaemon` starts (is_running=True), creates data_dir, stops cleanly (is_running=False)

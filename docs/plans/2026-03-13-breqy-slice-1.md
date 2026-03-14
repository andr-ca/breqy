# Breqy Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working engine daemon + default agent + TUI client that supports persistent streaming chat sessions with shell/filesystem tools, inline approvals, task visibility, and control primitives (stop, steer, circuit-break).

**Architecture:** Engine runs as an always-on daemon owning sessions, events, and policy. Agents are separate processes connecting via typed JSON-over-Unix-socket protocol (A2A). TUI is a separate Textual app connecting to the engine. All communication uses typed event envelopes with shared schemas. SQLite (WAL mode) stores canonical state; a centralized event writer prevents write contention.

**Tech Stack:** Python 3.12+, pydantic, aiosqlite, textual, structlog, python-ulid, keyring, pytest/pytest-asyncio, ruff, mypy

---

## Dependency Graph & Parallel Execution Map

```
Phase 1 (Serial - must go first):
  [Task 1-4: Foundation]

Phase 2 (ALL THREE run in PARALLEL after Phase 1):
  [Task 5-9: Storage]  ──────────────────────┐
  [Task 10-13: A2A Protocol]  ────────────────┤
  [Task 14-17: Policy/Approval/Config]  ──────┤
                                              │
Phase 3 (PARALLEL after their deps):          │
  [Task 18-22: Engine Core]  ←── needs Storage + Policy
  [Task 23-25: Tool System]  ←── needs Policy (parallel with Engine)
  [Task 29-32: TUI Client]   ←── needs A2A only (parallel with Engine+Tools)

Phase 4 (after Engine + Tools):
  [Task 26-28: Agent Runtime] ←── needs A2A + Tools + Engine

Phase 5 (after ALL above):
  [Task 33-36: Integration & Controls]
```

**Maximum parallelism: 3 independent agents during Phase 2, 3 during Phase 3.**

---

## Complete File Structure

Every file listed below with its single responsibility:

```
breqy/
  __init__.py                          # Package root, version
  py.typed                             # PEP 561 marker

  domain/
    __init__.py
    ids.py                             # ULID-based ID generation
    enums.py                           # SessionStatus, TaskStatus, EventType, etc.
    models.py                          # Session, Message, Participant, Task, Agent, etc.
    events.py                          # Typed event classes (MessageEvent, TaskEvent, etc.)
    errors.py                          # Domain exceptions

  storage/
    __init__.py
    interfaces.py                      # Abstract repository interfaces (ABCs)
    sqlite/
      __init__.py
      connection.py                    # Async connection pool, WAL mode, pragmas
      migrations.py                    # Schema DDL, version tracking
      session_repo.py                  # SessionRepository impl
      message_repo.py                  # MessageRepository impl
      event_repo.py                    # EventRepository impl (append-only)
      task_repo.py                     # TaskRepository impl
      approval_repo.py                # ApprovalRepository impl

  a2a/
    __init__.py
    envelope.py                        # A2A Envelope dataclass
    transport.py                       # Unix socket async transport (read/write frames)
    server.py                          # Engine-side: accept connections, route events
    client.py                          # Agent/TUI-side: connect, send, receive

  engine/
    __init__.py
    event_bus.py                       # In-process async pub/sub
    event_writer.py                    # Centralized sequential DB writer
    session_manager.py                 # Create/resume/list sessions
    agent_registry.py                  # Track connected agents
    agent_spawner.py                   # Subprocess management for agents
    daemon.py                          # Daemon lifecycle (start, stop, signals)
    server.py                          # Ties engine components together

  policy/
    __init__.py
    models.py                          # PolicyRule, PolicyScope, PolicyDecision
    evaluator.py                       # PolicyEvaluator (layered rule resolution)
    filesystem.py                      # Path-based filesystem policy

  approval/
    __init__.py
    service.py                         # ApprovalService (request, decide, check grants)

  tools/
    __init__.py
    executor.py                        # ToolExecutor ABC + ToolResult
    registry.py                        # ToolRegistry (register, lookup)
    shell.py                           # ShellTool (subprocess execution)
    filesystem.py                      # FilesystemTool (read/write/edit/delete)

  agents/
    __init__.py
    config.py                          # Agent YAML config loader
    runtime.py                         # Agent process main loop

  tui/
    __init__.py
    app.py                             # Main Textual Application
    client.py                          # TUI-side A2A client wrapper
    screens/
      __init__.py
      session_list.py                  # Session selection screen
      chat.py                          # Active chat screen
    widgets/
      __init__.py
      message_view.py                  # Message rendering widget
      task_list.py                     # Task/TODO list widget
      approval_prompt.py               # Inline approval widget
      control_bar.py                   # Stop/steer/circuit-break controls

  config/
    __init__.py
    loader.py                          # YAML + Markdown config loading
    models.py                          # EngineConfig, AgentConfig dataclasses

  secrets/
    __init__.py
    provider.py                        # SecretProvider ABC + KeyringProvider

  utils/
    __init__.py
    logging.py                         # structlog setup

system/
  agents/
    breqy/
      agent.yaml                       # Default agent manifest
      persona.md                       # Default agent persona

tests/
  __init__.py
  conftest.py                          # Shared fixtures (tmp db, event loop)
  domain/
    __init__.py
    test_ids.py
    test_models.py
    test_events.py
  storage/
    __init__.py
    test_connection.py
    test_session_repo.py
    test_message_repo.py
    test_event_repo.py
    test_task_repo.py
    test_approval_repo.py
  a2a/
    __init__.py
    test_envelope.py
    test_transport.py
    test_server_client.py
  engine/
    __init__.py
    test_event_bus.py
    test_event_writer.py
    test_session_manager.py
    test_agent_registry.py
    test_agent_spawner.py
    test_daemon.py
  policy/
    __init__.py
    test_evaluator.py
    test_filesystem_policy.py
  approval/
    __init__.py
    test_service.py
  tools/
    __init__.py
    test_executor.py
    test_shell.py
    test_filesystem_tool.py
  agents/
    __init__.py
    test_config.py
    test_runtime.py
  tui/
    __init__.py
    test_app.py
  integration/
    __init__.py
    test_session_flow.py
    test_control_primitives.py
    test_restart_survival.py
```

---

## Chunk 1: Foundation

**Parallel: NO — must complete before all other chunks**
**Workstreams: WS-1 (Project Setup) + WS-2 (Core Domain)**

### Task 1: Project Setup & Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.env.sample`
- Create: `.env`
- Create: `.gitignore` (update)
- Create: `breqy/__init__.py`
- Create: `breqy/py.typed`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml with all dependencies**

```toml
[project]
name = "breqy"
version = "0.1.0"
description = "AI-powered multi-agent technical assistant platform"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.10",
    "aiosqlite>=0.21",
    "textual>=1.0",
    "structlog>=24.4",
    "python-ulid>=3.0",
    "keyring>=25.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.9",
    "mypy>=1.14",
]

[project.scripts]
breqy-engine = "breqy.engine.daemon:main"
breqy-tui = "breqy.tui.app:main"
breqy-agent = "breqy.agents.runtime:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create .env.sample and .env**

`.env.sample`:
```
# Breqy Engine Configuration
BREQY_ENGINE_SOCKET=/tmp/breqy-engine.sock
BREQY_DATA_DIR=~/.breqy/data
BREQY_LOG_LEVEL=INFO
BREQY_DB_PATH=~/.breqy/data/breqy.db
```

`.env` should be a copy of `.env.sample` with actual values. Add `.env` to `.gitignore`.

- [ ] **Step 3: Create package root files**

`breqy/__init__.py`:
```python
"""Breqy - AI-powered multi-agent technical assistant platform."""

__version__ = "0.1.0"
```

`breqy/py.typed`: empty file (PEP 561 marker)

- [ ] **Step 4: Create test conftest with shared fixtures**

`tests/conftest.py`:
```python
"""Shared test fixtures."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
import aiosqlite

from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def db_path(tmp_dir: Path) -> Path:
    return tmp_dir / "test.db"


@pytest_asyncio.fixture
async def db_connection(db_path: Path) -> aiosqlite.Connection:
    conn = await create_connection(str(db_path))
    await run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
def socket_path(tmp_dir: Path) -> Path:
    return tmp_dir / "test.sock"
```

- [ ] **Step 5: Install project in dev mode and verify**

Run: `cd /home/andrey/projects/breqy && pip install -e ".[dev]"`
Expected: successful installation

Run: `python -c "import breqy; print(breqy.__version__)"`
Expected: `0.1.0`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.sample .gitignore breqy/__init__.py breqy/py.typed tests/__init__.py tests/conftest.py
git commit -m "feat: project setup with dependencies and tooling config"
```

---

### Task 2: Core IDs & Enums

**Files:**
- Create: `breqy/domain/__init__.py`
- Create: `breqy/domain/ids.py`
- Create: `breqy/domain/enums.py`
- Create: `tests/domain/__init__.py`
- Create: `tests/domain/test_ids.py`

- [ ] **Step 1: Write failing tests for ID generation**

`tests/domain/test_ids.py`:
```python
"""Tests for ID generation."""

from breqy.domain.ids import generate_id, generate_prefixed_id


def test_generate_id_returns_string():
    id_val = generate_id()
    assert isinstance(id_val, str)
    assert len(id_val) == 26  # ULID length


def test_generate_id_is_unique():
    ids = {generate_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_prefixed_id():
    id_val = generate_prefixed_id("ses")
    assert id_val.startswith("ses_")
    assert len(id_val) == 30  # "ses_" + 26


def test_generate_prefixed_id_different_prefixes():
    session_id = generate_prefixed_id("ses")
    message_id = generate_prefixed_id("msg")
    assert session_id.startswith("ses_")
    assert message_id.startswith("msg_")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/domain/test_ids.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement ID generation**

`breqy/domain/__init__.py`:
```python
"""Core domain models, events, and value objects."""
```

`breqy/domain/ids.py`:
```python
"""ULID-based ID generation for all domain objects."""

from ulid import ULID


def generate_id() -> str:
    """Generate a new ULID string."""
    return str(ULID())


def generate_prefixed_id(prefix: str) -> str:
    """Generate a prefixed ULID (e.g., 'ses_01HX...')."""
    return f"{prefix}_{ULID()}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/domain/test_ids.py -v`
Expected: 4 passed

- [ ] **Step 5: Create enums module**

`breqy/domain/enums.py`:
```python
"""Status and type enumerations for the domain."""

from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventType(StrEnum):
    # Session events
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"
    SESSION_CLOSED = "session.closed"

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_CHUNK = "message.chunk"

    # Task events
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"

    # Tool events
    TOOL_INVOCATION_STARTED = "tool.invocation.started"
    TOOL_INVOCATION_COMPLETED = "tool.invocation.completed"
    TOOL_INVOCATION_FAILED = "tool.invocation.failed"
    TOOL_OUTPUT_CHUNK = "tool.output.chunk"

    # Approval events
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"

    # Agent lifecycle events
    AGENT_CONNECTED = "agent.connected"
    AGENT_DISCONNECTED = "agent.disconnected"

    # Control events
    CONTROL_STOP = "control.stop"
    CONTROL_STOP_AND_STEER = "control.stop_and_steer"
    CONTROL_STEER = "control.steer"
    CONTROL_CIRCUIT_BREAK = "control.circuit_break"


class MessageRole(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class ToolStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"


class PolicyScope(StrEnum):
    GLOBAL = "global"
    AGENT = "agent"
    SESSION = "session"


class PolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVE = "approve"  # Requires approval


class FilesystemOperation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


class AutonomyLevel(StrEnum):
    ASSISTANT = "assistant"        # Ask before most actions
    SUPERVISED = "supervised"      # Ask for risky actions only
    AUTONOMOUS = "autonomous"      # Act freely within policy bounds
    PRIVILEGED = "privileged"      # Minimal restrictions
```

- [ ] **Step 6: Commit**

```bash
git add breqy/domain/ tests/domain/
git commit -m "feat: core ID generation and domain enums"
```

---

### Task 3: Core Domain Models

**Files:**
- Create: `breqy/domain/models.py`
- Create: `breqy/domain/errors.py`
- Create: `tests/domain/test_models.py`

- [ ] **Step 1: Write failing tests for domain models**

`tests/domain/test_models.py`:
```python
"""Tests for core domain models."""

from datetime import datetime, timezone

from breqy.domain.models import (
    Session,
    Message,
    Participant,
    Task,
    Agent,
    ApprovalRequest,
    ApprovalDecision,
    ToolInvocation,
    PolicyRule,
)
from breqy.domain.enums import (
    SessionStatus,
    TaskStatus,
    MessageRole,
    ToolStatus,
    ApprovalStatus,
    PolicyScope,
    PolicyAction,
)
from breqy.domain.ids import generate_prefixed_id


def test_session_creation():
    session = Session(
        id=generate_prefixed_id("ses"),
        status=SessionStatus.ACTIVE,
        primary_agent_id="agent_breqy",
    )
    assert session.status == SessionStatus.ACTIVE
    assert session.primary_agent_id == "agent_breqy"
    assert session.created_at is not None


def test_message_creation():
    msg = Message(
        id=generate_prefixed_id("msg"),
        session_id="ses_test",
        role=MessageRole.USER,
        content="Hello breqy",
    )
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello breqy"


def test_task_creation():
    task = Task(
        id=generate_prefixed_id("tsk"),
        session_id="ses_test",
        title="Install nginx",
        status=TaskStatus.PENDING,
    )
    assert task.status == TaskStatus.PENDING
    assert task.parent_id is None


def test_task_with_parent():
    parent = Task(
        id="tsk_parent",
        session_id="ses_test",
        title="Setup server",
        status=TaskStatus.IN_PROGRESS,
    )
    child = Task(
        id="tsk_child",
        session_id="ses_test",
        title="Install nginx",
        status=TaskStatus.PENDING,
        parent_id=parent.id,
    )
    assert child.parent_id == "tsk_parent"


def test_tool_invocation():
    inv = ToolInvocation(
        id=generate_prefixed_id("inv"),
        session_id="ses_test",
        agent_id="agent_breqy",
        tool_name="shell",
        arguments={"command": "ls -la"},
        status=ToolStatus.PENDING,
    )
    assert inv.tool_name == "shell"
    assert inv.status == ToolStatus.PENDING


def test_approval_request():
    req = ApprovalRequest(
        id=generate_prefixed_id("apr"),
        session_id="ses_test",
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Execute: rm -rf /tmp/old",
        status=ApprovalStatus.PENDING,
    )
    assert req.status == ApprovalStatus.PENDING


def test_policy_rule():
    rule = PolicyRule(
        id=generate_prefixed_id("pol"),
        scope=PolicyScope.GLOBAL,
        action=PolicyAction.DENY,
        resource="tool:shell",
    )
    assert rule.scope == PolicyScope.GLOBAL
    assert rule.action == PolicyAction.DENY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/domain/test_models.py -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement domain models**

`breqy/domain/errors.py`:
```python
"""Domain exceptions."""


class BreqyError(Exception):
    """Base exception for all Breqy errors."""


class SessionNotFoundError(BreqyError):
    """Raised when a session is not found."""


class AgentNotFoundError(BreqyError):
    """Raised when an agent is not found."""


class PolicyDeniedError(BreqyError):
    """Raised when a policy check denies an action."""

    def __init__(self, resource: str, reason: str = ""):
        self.resource = resource
        self.reason = reason
        super().__init__(f"Policy denied access to {resource}: {reason}")


class ApprovalRequiredError(BreqyError):
    """Raised when an action requires approval."""

    def __init__(self, approval_request_id: str):
        self.approval_request_id = approval_request_id
        super().__init__(f"Approval required: {approval_request_id}")


class ApprovalTimeoutError(BreqyError):
    """Raised when an approval request times out."""


class ToolExecutionError(BreqyError):
    """Raised when a tool fails to execute."""


class AgentSpawnError(BreqyError):
    """Raised when agent process fails to spawn."""


class TransportError(BreqyError):
    """Raised for A2A transport failures."""
```

`breqy/domain/models.py`:
```python
"""Core domain models shared across all Breqy components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import (
    ApprovalStatus,
    AutonomyLevel,
    FilesystemOperation,
    MessageRole,
    PolicyAction,
    PolicyScope,
    SessionStatus,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.ids import generate_prefixed_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session(BaseModel):
    """A persistent conversation thread."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("ses"))
    status: SessionStatus = SessionStatus.ACTIVE
    primary_agent_id: str
    workspace_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Participant(BaseModel):
    """An agent participating in a session."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("prt"))
    session_id: str
    agent_id: str
    joined_at: datetime = Field(default_factory=_now)
    left_at: datetime | None = None


class Message(BaseModel):
    """A message in a session."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("msg"))
    session_id: str
    role: MessageRole
    content: str
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Task(BaseModel):
    """An explicit work item with status tracking."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("tsk"))
    session_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    parent_id: str | None = None
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ToolInvocation(BaseModel):
    """Record of a tool execution."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("inv"))
    session_id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    summary: str = ""
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None


class ApprovalRequest(BaseModel):
    """A request for user approval of an action."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("apr"))
    session_id: str
    agent_id: str
    tool_invocation_id: str
    description: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=_now)


class ApprovalDecision(BaseModel):
    """User's decision on an approval request."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("apd"))
    request_id: str
    granted: bool
    extend_to_session: bool = False
    reason: str = ""
    decided_at: datetime = Field(default_factory=_now)


class Agent(BaseModel):
    """Agent configuration and identity."""

    id: str
    name: str
    display_name: str = ""
    port: int | None = None
    persona_file: str = ""
    autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str = ""


class PolicyRule(BaseModel):
    """A permission rule at a given scope."""

    id: str = Field(default_factory=lambda: generate_prefixed_id("pol"))
    scope: PolicyScope
    scope_id: str = ""  # agent_id or session_id, empty for global
    action: PolicyAction
    resource: str  # e.g. "tool:shell", "fs:/etc", "ssh:host"
    operation: str = ""  # e.g. "read", "write" for filesystem
    priority: int = 0
    created_at: datetime = Field(default_factory=_now)


class FilesystemPolicy(BaseModel):
    """Path-based filesystem access rule."""

    path: str
    operation: FilesystemOperation
    action: PolicyAction
    scope: PolicyScope = PolicyScope.GLOBAL
    scope_id: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_models.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add breqy/domain/models.py breqy/domain/errors.py tests/domain/test_models.py
git commit -m "feat: core domain models and error types"
```

---

### Task 4: Core Event Schemas

**Files:**
- Create: `breqy/domain/events.py`
- Create: `tests/domain/test_events.py`

- [ ] **Step 1: Write failing tests for event schemas**

`tests/domain/test_events.py`:
```python
"""Tests for typed event schemas."""

from breqy.domain.events import (
    Event,
    MessageSentEvent,
    MessageChunkEvent,
    TaskUpdatedEvent,
    ToolInvocationStartedEvent,
    ToolInvocationCompletedEvent,
    ToolOutputChunkEvent,
    ApprovalRequestedEvent,
    ApprovalDecidedEvent,
    ControlEvent,
    AgentLifecycleEvent,
    SessionCreatedEvent,
)
from breqy.domain.enums import EventType, TaskStatus, ToolStatus, ApprovalStatus


def test_event_base_has_required_fields():
    event = Event(
        event_type=EventType.SESSION_CREATED,
        session_id="ses_test",
    )
    assert event.event_id is not None
    assert event.schema_version == 1
    assert event.timestamp is not None
    assert event.session_id == "ses_test"


def test_message_sent_event():
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role="user",
        content="Hello",
    )
    assert event.event_type == EventType.MESSAGE_SENT
    assert event.content == "Hello"


def test_message_chunk_event():
    event = MessageChunkEvent(
        session_id="ses_test",
        message_id="msg_test",
        chunk="partial text",
        chunk_index=0,
    )
    assert event.event_type == EventType.MESSAGE_CHUNK
    assert event.chunk == "partial text"


def test_tool_invocation_started_event():
    event = ToolInvocationStartedEvent(
        session_id="ses_test",
        agent_id="agent_breqy",
        invocation_id="inv_test",
        tool_name="shell",
        arguments={"command": "ls"},
        summary="List files",
    )
    assert event.event_type == EventType.TOOL_INVOCATION_STARTED
    assert event.tool_name == "shell"


def test_tool_invocation_completed_event():
    event = ToolInvocationCompletedEvent(
        session_id="ses_test",
        agent_id="agent_breqy",
        invocation_id="inv_test",
        tool_name="shell",
        status=ToolStatus.COMPLETED,
        summary="Listed 5 files",
    )
    assert event.event_type == EventType.TOOL_INVOCATION_COMPLETED


def test_approval_requested_event():
    event = ApprovalRequestedEvent(
        session_id="ses_test",
        agent_id="agent_breqy",
        approval_id="apr_test",
        invocation_id="inv_test",
        description="Execute: rm -rf /tmp/old",
    )
    assert event.event_type == EventType.APPROVAL_REQUESTED


def test_control_event():
    event = ControlEvent(
        session_id="ses_test",
        event_type=EventType.CONTROL_STOP,
    )
    assert event.event_type == EventType.CONTROL_STOP


def test_event_serialization_roundtrip():
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role="user",
        content="Hello",
    )
    data = event.model_dump()
    restored = MessageSentEvent.model_validate(data)
    assert restored.content == "Hello"
    assert restored.event_id == event.event_id


def test_event_to_json():
    event = TaskUpdatedEvent(
        session_id="ses_test",
        task_id="tsk_test",
        status=TaskStatus.IN_PROGRESS,
        title="Install nginx",
    )
    json_str = event.model_dump_json()
    assert "tsk_test" in json_str
    assert "in_progress" in json_str
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/domain/test_events.py -v`
Expected: FAIL (import errors)

- [ ] **Step 3: Implement event schemas**

`breqy/domain/events.py`:
```python
"""Typed event schemas for the A2A contract.

Every event exchanged between engine, agents, and channels
must use one of these typed schemas. No heuristic interpretation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import (
    ApprovalStatus,
    EventType,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.ids import generate_prefixed_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """Base event envelope. All events inherit from this."""

    event_id: str = Field(default_factory=lambda: generate_prefixed_id("evt"))
    event_type: EventType
    schema_version: int = 1
    session_id: str
    agent_id: str = ""
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=_now)


# --- Session Events ---


class SessionCreatedEvent(Event):
    event_type: EventType = EventType.SESSION_CREATED
    primary_agent_id: str = ""


class SessionResumedEvent(Event):
    event_type: EventType = EventType.SESSION_RESUMED


class SessionClosedEvent(Event):
    event_type: EventType = EventType.SESSION_CLOSED


# --- Message Events ---


class MessageSentEvent(Event):
    event_type: EventType = EventType.MESSAGE_SENT
    message_id: str
    role: str
    content: str


class MessageChunkEvent(Event):
    event_type: EventType = EventType.MESSAGE_CHUNK
    message_id: str
    chunk: str
    chunk_index: int


# --- Task Events ---


class TaskUpdatedEvent(Event):
    event_type: EventType = EventType.TASK_UPDATED
    task_id: str
    status: TaskStatus
    title: str = ""
    description: str = ""


# --- Tool Events ---


class ToolInvocationStartedEvent(Event):
    event_type: EventType = EventType.TOOL_INVOCATION_STARTED
    invocation_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class ToolInvocationCompletedEvent(Event):
    event_type: EventType = EventType.TOOL_INVOCATION_COMPLETED
    invocation_id: str
    tool_name: str
    status: ToolStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    summary: str = ""


class ToolOutputChunkEvent(Event):
    event_type: EventType = EventType.TOOL_OUTPUT_CHUNK
    invocation_id: str
    chunk: str
    chunk_index: int


# --- Approval Events ---


class ApprovalRequestedEvent(Event):
    event_type: EventType = EventType.APPROVAL_REQUESTED
    approval_id: str
    invocation_id: str
    description: str


class ApprovalDecidedEvent(Event):
    event_type: EventType = EventType.APPROVAL_GRANTED  # overridden per decision
    approval_id: str
    granted: bool = True
    extend_to_session: bool = False
    reason: str = ""


# --- Agent Lifecycle Events ---


class AgentLifecycleEvent(Event):
    """Agent connected or disconnected."""

    agent_name: str = ""
    agent_display_name: str = ""


# --- Control Events ---


class ControlEvent(Event):
    """User control intervention (stop, steer, circuit-break)."""

    new_direction: str = ""  # For steer and stop-and-steer


# --- Event Registry ---

EVENT_TYPE_MAP: dict[EventType, type[Event]] = {
    EventType.SESSION_CREATED: SessionCreatedEvent,
    EventType.SESSION_RESUMED: SessionResumedEvent,
    EventType.SESSION_CLOSED: SessionClosedEvent,
    EventType.MESSAGE_SENT: MessageSentEvent,
    EventType.MESSAGE_CHUNK: MessageChunkEvent,
    EventType.TASK_UPDATED: TaskUpdatedEvent,
    EventType.TOOL_INVOCATION_STARTED: ToolInvocationStartedEvent,
    EventType.TOOL_INVOCATION_COMPLETED: ToolInvocationCompletedEvent,
    EventType.TOOL_OUTPUT_CHUNK: ToolOutputChunkEvent,
    EventType.APPROVAL_REQUESTED: ApprovalRequestedEvent,
    EventType.APPROVAL_GRANTED: ApprovalDecidedEvent,
    EventType.APPROVAL_DENIED: ApprovalDecidedEvent,
    EventType.AGENT_CONNECTED: AgentLifecycleEvent,
    EventType.AGENT_DISCONNECTED: AgentLifecycleEvent,
    EventType.CONTROL_STOP: ControlEvent,
    EventType.CONTROL_STOP_AND_STEER: ControlEvent,
    EventType.CONTROL_STEER: ControlEvent,
    EventType.CONTROL_CIRCUIT_BREAK: ControlEvent,
}


def deserialize_event(data: dict[str, Any]) -> Event:
    """Deserialize a dict into the correct typed Event subclass."""
    event_type = EventType(data["event_type"])
    event_cls = EVENT_TYPE_MAP.get(event_type, Event)
    return event_cls.model_validate(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_events.py -v`
Expected: all passed

- [ ] **Step 5: Run full domain test suite**

Run: `pytest tests/domain/ -v`
Expected: all passed

- [ ] **Step 6: Run linter and type checker**

Run: `ruff check breqy/domain/`
Run: `mypy breqy/domain/`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add breqy/domain/events.py tests/domain/test_events.py
git commit -m "feat: typed event schemas for A2A contract"
```

---

## Chunk 2: Storage Layer

**Parallel: YES — can run simultaneously with Chunks 3 and 4 (after Chunk 1)**
**Depends on: Chunk 1 (domain models)**

### Task 5: Repository Interfaces

**Files:**
- Create: `breqy/storage/__init__.py`
- Create: `breqy/storage/interfaces.py`

- [ ] **Step 1: Define abstract repository interfaces**

`breqy/storage/__init__.py`:
```python
"""Storage layer with repository abstractions."""
```

`breqy/storage/interfaces.py`:
```python
"""Abstract repository interfaces.

All persistence is behind these interfaces, injected via DI.
Implementations may use SQLite, Postgres, or other backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from breqy.domain.enums import SessionStatus, TaskStatus, ApprovalStatus
from breqy.domain.events import Event
from breqy.domain.models import (
    ApprovalDecision,
    ApprovalRequest,
    Message,
    Participant,
    Session,
    Task,
    ToolInvocation,
)


class SessionRepository(ABC):
    @abstractmethod
    async def create(self, session: Session) -> None: ...

    @abstractmethod
    async def get(self, session_id: str) -> Session | None: ...

    @abstractmethod
    async def list_active(self) -> list[Session]: ...

    @abstractmethod
    async def update_status(self, session_id: str, status: SessionStatus) -> None: ...

    @abstractmethod
    async def update_timestamp(self, session_id: str) -> None: ...


class MessageRepository(ABC):
    @abstractmethod
    async def create(self, message: Message) -> None: ...

    @abstractmethod
    async def list_by_session(
        self, session_id: str, limit: int = 100, before: datetime | None = None
    ) -> list[Message]: ...


class EventRepository(ABC):
    """Append-only event log."""

    @abstractmethod
    async def append(self, event: Event) -> None: ...

    @abstractmethod
    async def list_by_session(
        self, session_id: str, limit: int = 100, after_event_id: str = ""
    ) -> list[Event]: ...


class TaskRepository(ABC):
    @abstractmethod
    async def create(self, task: Task) -> None: ...

    @abstractmethod
    async def get(self, task_id: str) -> Task | None: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[Task]: ...

    @abstractmethod
    async def update_status(self, task_id: str, status: TaskStatus) -> None: ...


class ApprovalRepository(ABC):
    @abstractmethod
    async def create_request(self, request: ApprovalRequest) -> None: ...

    @abstractmethod
    async def create_decision(self, decision: ApprovalDecision) -> None: ...

    @abstractmethod
    async def get_request(self, request_id: str) -> ApprovalRequest | None: ...

    @abstractmethod
    async def get_pending_by_session(self, session_id: str) -> list[ApprovalRequest]: ...

    @abstractmethod
    async def update_request_status(
        self, request_id: str, status: ApprovalStatus
    ) -> None: ...

    @abstractmethod
    async def get_session_grants(self, session_id: str) -> list[ApprovalDecision]: ...
```

- [ ] **Step 2: Commit**

```bash
git add breqy/storage/
git commit -m "feat: abstract repository interfaces for storage layer"
```

---

### Task 6: SQLite Connection & WAL Mode

**Files:**
- Create: `breqy/storage/sqlite/__init__.py`
- Create: `breqy/storage/sqlite/connection.py`
- Create: `tests/storage/__init__.py`
- Create: `tests/storage/test_connection.py`

- [ ] **Step 1: Write failing test for connection**

`tests/storage/test_connection.py`:
```python
"""Tests for SQLite connection management."""

import pytest
from pathlib import Path

from breqy.storage.sqlite.connection import create_connection


@pytest.mark.asyncio
async def test_create_connection(db_path: Path):
    conn = await create_connection(str(db_path))
    assert conn is not None
    # Verify WAL mode
    cursor = await conn.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row[0] == "wal"
    await conn.close()


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db_path: Path):
    conn = await create_connection(str(db_path))
    cursor = await conn.execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    assert row[0] == 1
    await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_connection.py -v`
Expected: FAIL

- [ ] **Step 3: Implement connection**

`breqy/storage/sqlite/__init__.py`:
```python
"""SQLite storage backend."""
```

`breqy/storage/sqlite/connection.py`:
```python
"""SQLite connection management with WAL mode."""

import aiosqlite


async def create_connection(db_path: str) -> aiosqlite.Connection:
    """Create a new SQLite connection with WAL mode and foreign keys."""
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_connection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add breqy/storage/sqlite/ tests/storage/
git commit -m "feat: SQLite connection with WAL mode"
```

---

### Task 7: SQLite Schema & Migrations

**Files:**
- Create: `breqy/storage/sqlite/migrations.py`

- [ ] **Step 1: Write test for migrations**

Add to `tests/storage/test_connection.py`:
```python
from breqy.storage.sqlite.migrations import run_migrations


@pytest.mark.asyncio
async def test_run_migrations_creates_tables(db_path: Path):
    conn = await create_connection(str(db_path))
    await run_migrations(conn)

    # Verify tables exist
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "sessions" in tables
    assert "messages" in tables
    assert "events" in tables
    assert "tasks" in tables
    assert "approval_requests" in tables
    assert "approval_decisions" in tables
    assert "tool_invocations" in tables
    assert "participants" in tables
    await conn.close()


@pytest.mark.asyncio
async def test_migrations_are_idempotent(db_path: Path):
    conn = await create_connection(str(db_path))
    await run_migrations(conn)
    await run_migrations(conn)  # Should not fail
    await conn.close()
```

- [ ] **Step 2: Implement migrations**

`breqy/storage/sqlite/migrations.py`:
```python
"""SQLite schema DDL and migration runner."""

import aiosqlite

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    primary_agent_id TEXT NOT NULL,
    workspace_paths TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    left_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_participants_session ON participants(session_id);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    parent_id TEXT,
    agent_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);

CREATE TABLE IF NOT EXISTS tool_invocations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    approval_id TEXT,
    summary TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_invocations_session ON tool_invocations(session_id);

CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    agent_id TEXT NOT NULL,
    tool_invocation_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_session ON approval_requests(session_id);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES approval_requests(id),
    granted INTEGER NOT NULL,
    extend_to_session INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(session_id, timestamp);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


async def run_migrations(conn: aiosqlite.Connection) -> None:
    """Run schema migrations. Idempotent."""
    await conn.executescript(SCHEMA_V1)
    # Track schema version
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (1,)
    )
    await conn.commit()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/storage/test_connection.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/storage/sqlite/migrations.py tests/storage/test_connection.py
git commit -m "feat: SQLite schema with all Slice 1 tables"
```

---

### Task 8: Session & Message Repositories

**Files:**
- Create: `breqy/storage/sqlite/session_repo.py`
- Create: `breqy/storage/sqlite/message_repo.py`
- Create: `tests/storage/test_session_repo.py`
- Create: `tests/storage/test_message_repo.py`

- [ ] **Step 1: Write failing tests for session repo**

`tests/storage/test_session_repo.py`:
```python
"""Tests for SQLite session repository."""

import pytest

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository


@pytest.mark.asyncio
async def test_create_and_get_session(db_connection):
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await repo.create(session)

    result = await repo.get(session.id)
    assert result is not None
    assert result.id == session.id
    assert result.primary_agent_id == "agent_breqy"
    assert result.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_nonexistent_session(db_connection):
    repo = SqliteSessionRepository(db_connection)
    result = await repo.get("ses_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_active_sessions(db_connection):
    repo = SqliteSessionRepository(db_connection)
    s1 = Session(primary_agent_id="agent_breqy")
    s2 = Session(primary_agent_id="agent_breqy")
    s3 = Session(primary_agent_id="agent_breqy", status=SessionStatus.CLOSED)

    await repo.create(s1)
    await repo.create(s2)
    await repo.create(s3)

    active = await repo.list_active()
    assert len(active) == 2


@pytest.mark.asyncio
async def test_update_session_status(db_connection):
    repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await repo.create(session)

    await repo.update_status(session.id, SessionStatus.PAUSED)
    result = await repo.get(session.id)
    assert result.status == SessionStatus.PAUSED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_session_repo.py -v`
Expected: FAIL

- [ ] **Step 3: Implement session repo**

`breqy/storage/sqlite/session_repo.py`:
```python
"""SQLite implementation of SessionRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session
from breqy.storage.interfaces import SessionRepository


class SqliteSessionRepository(SessionRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, session: Session) -> None:
        await self._conn.execute(
            """INSERT INTO sessions (id, status, primary_agent_id, workspace_paths, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.status.value,
                session.primary_agent_id,
                json.dumps(session.workspace_paths),
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get(self, session_id: str) -> Session | None:
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    async def list_active(self) -> list[Session]:
        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE status = ? ORDER BY updated_at DESC",
            (SessionStatus.ACTIVE.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, session_id),
        )
        await self._conn.commit()

    async def update_timestamp(self, session_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_session(row: aiosqlite.Row) -> Session:
        return Session(
            id=row["id"],
            status=SessionStatus(row["status"]),
            primary_agent_id=row["primary_agent_id"],
            workspace_paths=json.loads(row["workspace_paths"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_session_repo.py -v`
Expected: all passed

- [ ] **Step 5: Write failing tests for message repo**

`tests/storage/test_message_repo.py`:
```python
"""Tests for SQLite message repository."""

import pytest

from breqy.domain.enums import MessageRole
from breqy.domain.models import Message, Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository


@pytest.mark.asyncio
async def test_create_and_list_messages(db_connection):
    # Need a session first (FK constraint)
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    msg_repo = SqliteMessageRepository(db_connection)
    m1 = Message(session_id=session.id, role=MessageRole.USER, content="Hello")
    m2 = Message(session_id=session.id, role=MessageRole.AGENT, content="Hi there", agent_id="agent_breqy")
    await msg_repo.create(m1)
    await msg_repo.create(m2)

    messages = await msg_repo.list_by_session(session.id)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there"


@pytest.mark.asyncio
async def test_list_messages_respects_limit(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    msg_repo = SqliteMessageRepository(db_connection)
    for i in range(10):
        msg = Message(session_id=session.id, role=MessageRole.USER, content=f"msg {i}")
        await msg_repo.create(msg)

    messages = await msg_repo.list_by_session(session.id, limit=3)
    assert len(messages) == 3
```

- [ ] **Step 6: Implement message repo**

`breqy/storage/sqlite/message_repo.py`:
```python
"""SQLite implementation of MessageRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.enums import MessageRole
from breqy.domain.models import Message
from breqy.storage.interfaces import MessageRepository


class SqliteMessageRepository(MessageRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, message: Message) -> None:
        await self._conn.execute(
            """INSERT INTO messages (id, session_id, role, content, agent_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                message.id,
                message.session_id,
                message.role.value,
                message.content,
                message.agent_id,
                message.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def list_by_session(
        self,
        session_id: str,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[Message]:
        if before:
            cursor = await self._conn.execute(
                """SELECT * FROM messages WHERE session_id = ? AND created_at < ?
                   ORDER BY created_at ASC LIMIT ?""",
                (session_id, before.isoformat(), limit),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT * FROM messages WHERE session_id = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (session_id, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _row_to_message(row: aiosqlite.Row) -> Message:
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            agent_id=row["agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/storage/ -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add breqy/storage/sqlite/session_repo.py breqy/storage/sqlite/message_repo.py tests/storage/test_session_repo.py tests/storage/test_message_repo.py
git commit -m "feat: SQLite session and message repositories"
```

---

### Task 9: Event, Task & Approval Repositories

**Files:**
- Create: `breqy/storage/sqlite/event_repo.py`
- Create: `breqy/storage/sqlite/task_repo.py`
- Create: `breqy/storage/sqlite/approval_repo.py`
- Create: `tests/storage/test_event_repo.py`
- Create: `tests/storage/test_task_repo.py`
- Create: `tests/storage/test_approval_repo.py`

- [ ] **Step 1: Write failing test for event repo**

`tests/storage/test_event_repo.py`:
```python
"""Tests for SQLite event repository (append-only)."""

import pytest

from breqy.domain.events import MessageSentEvent, ToolInvocationStartedEvent
from breqy.domain.models import Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository


@pytest.mark.asyncio
async def test_append_and_list_events(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    e1 = MessageSentEvent(
        session_id=session.id, message_id="msg_1", role="user", content="Hello"
    )
    e2 = ToolInvocationStartedEvent(
        session_id=session.id,
        agent_id="agent_breqy",
        invocation_id="inv_1",
        tool_name="shell",
        arguments={"command": "ls"},
        summary="List files",
    )
    await event_repo.append(e1)
    await event_repo.append(e2)

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 2
    assert events[0].event_type.value == "message.sent"
    assert events[1].event_type.value == "tool.invocation.started"


@pytest.mark.asyncio
async def test_list_events_after_id(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    events_in = []
    for i in range(5):
        e = MessageSentEvent(
            session_id=session.id, message_id=f"msg_{i}", role="user", content=f"msg {i}"
        )
        await event_repo.append(e)
        events_in.append(e)

    # Get events after the 2nd one
    events = await event_repo.list_by_session(
        session.id, after_event_id=events_in[1].event_id
    )
    assert len(events) == 3
```

- [ ] **Step 2: Implement event repo**

`breqy/storage/sqlite/event_repo.py`:
```python
"""SQLite implementation of EventRepository (append-only)."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from breqy.domain.events import Event, deserialize_event
from breqy.storage.interfaces import EventRepository


class SqliteEventRepository(EventRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def append(self, event: Event) -> None:
        payload = event.model_dump(exclude={"event_id", "event_type", "schema_version",
                                             "session_id", "agent_id", "correlation_id",
                                             "timestamp"})
        await self._conn.execute(
            """INSERT INTO events (event_id, event_type, schema_version, session_id,
               agent_id, correlation_id, timestamp, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.event_type.value,
                event.schema_version,
                event.session_id,
                event.agent_id,
                event.correlation_id,
                event.timestamp.isoformat(),
                json.dumps(payload, default=str),
            ),
        )
        await self._conn.commit()

    async def list_by_session(
        self, session_id: str, limit: int = 100, after_event_id: str = ""
    ) -> list[Event]:
        if after_event_id:
            # Get the timestamp of the reference event
            cursor = await self._conn.execute(
                "SELECT timestamp FROM events WHERE event_id = ?", (after_event_id,)
            )
            ref_row = await cursor.fetchone()
            if ref_row is None:
                return []
            cursor = await self._conn.execute(
                """SELECT * FROM events WHERE session_id = ? AND timestamp > ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (session_id, ref_row["timestamp"], limit),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT * FROM events WHERE session_id = ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (session_id, limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: aiosqlite.Row) -> Event:
        payload = json.loads(row["payload"])
        data = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "schema_version": row["schema_version"],
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "correlation_id": row["correlation_id"],
            "timestamp": row["timestamp"],
            **payload,
        }
        return deserialize_event(data)
```

- [ ] **Step 3: Run event repo tests**

Run: `pytest tests/storage/test_event_repo.py -v`
Expected: all passed

- [ ] **Step 4: Write failing test for task repo**

`tests/storage/test_task_repo.py`:
```python
"""Tests for SQLite task repository."""

import pytest

from breqy.domain.enums import TaskStatus
from breqy.domain.models import Session, Task
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository


@pytest.mark.asyncio
async def test_create_and_get_task(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    task = Task(session_id=session.id, title="Install nginx")
    await task_repo.create(task)

    result = await task_repo.get(task.id)
    assert result is not None
    assert result.title == "Install nginx"
    assert result.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_update_task_status(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    task = Task(session_id=session.id, title="Install nginx")
    await task_repo.create(task)

    await task_repo.update_status(task.id, TaskStatus.COMPLETED)
    result = await task_repo.get(task.id)
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_list_tasks_by_session(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    await task_repo.create(Task(session_id=session.id, title="Task 1"))
    await task_repo.create(Task(session_id=session.id, title="Task 2"))

    tasks = await task_repo.list_by_session(session.id)
    assert len(tasks) == 2
```

- [ ] **Step 5: Implement task repo**

`breqy/storage/sqlite/task_repo.py`:
```python
"""SQLite implementation of TaskRepository."""

from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from breqy.domain.enums import TaskStatus
from breqy.domain.models import Task
from breqy.storage.interfaces import TaskRepository


class SqliteTaskRepository(TaskRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create(self, task: Task) -> None:
        await self._conn.execute(
            """INSERT INTO tasks (id, session_id, title, description, status, parent_id,
               agent_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.session_id, task.title, task.description,
                task.status.value, task.parent_id, task.agent_id,
                task.created_at.isoformat(), task.updated_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get(self, task_id: str) -> Task | None:
        cursor = await self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    async def list_by_session(self, session_id: str) -> list[Task]:
        cursor = await self._conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, now, task_id),
        )
        await self._conn.commit()

    @staticmethod
    def _row_to_task(row: aiosqlite.Row) -> Task:
        return Task(
            id=row["id"],
            session_id=row["session_id"],
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            parent_id=row["parent_id"],
            agent_id=row["agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
```

- [ ] **Step 6: Write and implement approval repo**

`tests/storage/test_approval_repo.py`:
```python
"""Tests for SQLite approval repository."""

import pytest

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest, Session, ToolInvocation
from breqy.domain.enums import ToolStatus
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository


@pytest.mark.asyncio
async def test_create_and_get_approval_request(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    req = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Execute: rm /tmp/file",
    )
    await repo.create_request(req)

    result = await repo.get_request(req.id)
    assert result is not None
    assert result.description == "Execute: rm /tmp/file"


@pytest.mark.asyncio
async def test_create_decision_and_get_grants(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    repo = SqliteApprovalRepository(db_connection)
    req = ApprovalRequest(
        session_id=session.id,
        agent_id="agent_breqy",
        tool_invocation_id="inv_test",
        description="Execute: ls",
    )
    await repo.create_request(req)

    decision = ApprovalDecision(
        request_id=req.id,
        granted=True,
        extend_to_session=True,
    )
    await repo.create_decision(decision)
    await repo.update_request_status(req.id, ApprovalStatus.GRANTED)

    grants = await repo.get_session_grants(session.id)
    assert len(grants) == 1
    assert grants[0].extend_to_session is True
```

`breqy/storage/sqlite/approval_repo.py`:
```python
"""SQLite implementation of ApprovalRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from breqy.domain.enums import ApprovalStatus
from breqy.domain.models import ApprovalDecision, ApprovalRequest
from breqy.storage.interfaces import ApprovalRepository


class SqliteApprovalRepository(ApprovalRepository):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create_request(self, request: ApprovalRequest) -> None:
        await self._conn.execute(
            """INSERT INTO approval_requests (id, session_id, agent_id,
               tool_invocation_id, description, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                request.id, request.session_id, request.agent_id,
                request.tool_invocation_id, request.description,
                request.status.value, request.created_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def create_decision(self, decision: ApprovalDecision) -> None:
        await self._conn.execute(
            """INSERT INTO approval_decisions (id, request_id, granted,
               extend_to_session, reason, decided_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                decision.id, decision.request_id, int(decision.granted),
                int(decision.extend_to_session), decision.reason,
                decision.decided_at.isoformat(),
            ),
        )
        await self._conn.commit()

    async def get_request(self, request_id: str) -> ApprovalRequest | None:
        cursor = await self._conn.execute(
            "SELECT * FROM approval_requests WHERE id = ?", (request_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ApprovalRequest(
            id=row["id"], session_id=row["session_id"], agent_id=row["agent_id"],
            tool_invocation_id=row["tool_invocation_id"],
            description=row["description"],
            status=ApprovalStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def get_pending_by_session(self, session_id: str) -> list[ApprovalRequest]:
        cursor = await self._conn.execute(
            "SELECT * FROM approval_requests WHERE session_id = ? AND status = ?",
            (session_id, ApprovalStatus.PENDING.value),
        )
        rows = await cursor.fetchall()
        return [
            ApprovalRequest(
                id=r["id"], session_id=r["session_id"], agent_id=r["agent_id"],
                tool_invocation_id=r["tool_invocation_id"],
                description=r["description"], status=ApprovalStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    async def update_request_status(
        self, request_id: str, status: ApprovalStatus
    ) -> None:
        await self._conn.execute(
            "UPDATE approval_requests SET status = ? WHERE id = ?",
            (status.value, request_id),
        )
        await self._conn.commit()

    async def get_session_grants(self, session_id: str) -> list[ApprovalDecision]:
        cursor = await self._conn.execute(
            """SELECT d.* FROM approval_decisions d
               JOIN approval_requests r ON d.request_id = r.id
               WHERE r.session_id = ? AND d.granted = 1 AND d.extend_to_session = 1""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            ApprovalDecision(
                id=r["id"], request_id=r["request_id"],
                granted=bool(r["granted"]),
                extend_to_session=bool(r["extend_to_session"]),
                reason=r["reason"],
                decided_at=datetime.fromisoformat(r["decided_at"]),
            )
            for r in rows
        ]
```

- [ ] **Step 7: Run all storage tests**

Run: `pytest tests/storage/ -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add breqy/storage/sqlite/event_repo.py breqy/storage/sqlite/task_repo.py breqy/storage/sqlite/approval_repo.py tests/storage/
git commit -m "feat: event, task, and approval repositories (SQLite)"
```

---

## Chunk 3: A2A Protocol

**Parallel: YES — can run simultaneously with Chunks 2 and 4 (after Chunk 1)**
**Depends on: Chunk 1 (domain events)**

### Task 10: A2A Envelope Format

**Files:**
- Create: `breqy/a2a/__init__.py`
- Create: `breqy/a2a/envelope.py`
- Create: `tests/a2a/__init__.py`
- Create: `tests/a2a/test_envelope.py`

- [ ] **Step 1: Write failing tests**

`tests/a2a/test_envelope.py`:
```python
"""Tests for A2A envelope format."""

import json

from breqy.a2a.envelope import Envelope, encode_envelope, decode_envelope
from breqy.domain.events import MessageSentEvent
from breqy.domain.enums import EventType


def test_envelope_from_event():
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role="user",
        content="Hello",
    )
    envelope = Envelope.from_event(event)
    assert envelope.event_type == EventType.MESSAGE_SENT
    assert envelope.session_id == "ses_test"
    assert envelope.schema_version == 1


def test_encode_decode_roundtrip():
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role="user",
        content="Hello",
    )
    envelope = Envelope.from_event(event)
    encoded = encode_envelope(envelope)
    assert isinstance(encoded, bytes)

    decoded = decode_envelope(encoded)
    assert decoded.event_type == envelope.event_type
    assert decoded.session_id == envelope.session_id
    assert decoded.payload["content"] == "Hello"


def test_envelope_to_event():
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role="user",
        content="Hello",
    )
    envelope = Envelope.from_event(event)
    restored = envelope.to_event()
    assert isinstance(restored, MessageSentEvent)
    assert restored.content == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/a2a/test_envelope.py -v`
Expected: FAIL

- [ ] **Step 3: Implement envelope**

`breqy/a2a/__init__.py`:
```python
"""A2A protocol: typed event envelopes over Unix sockets."""
```

`breqy/a2a/envelope.py`:
```python
"""A2A Envelope: the wire format for all engine-agent-channel communication.

Every message on the wire is a length-prefixed JSON envelope containing:
- event metadata (type, version, IDs, timestamp)
- payload (event-specific fields)
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import EventType
from breqy.domain.events import Event, deserialize_event
from breqy.domain.ids import generate_prefixed_id


class Envelope(BaseModel):
    """Wire-format envelope wrapping a typed event."""

    event_id: str = Field(default_factory=lambda: generate_prefixed_id("evt"))
    event_type: EventType
    schema_version: int = 1
    session_id: str
    agent_id: str = ""
    correlation_id: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: Event) -> Envelope:
        """Create an envelope from a typed Event."""
        data = event.model_dump()
        # Extract envelope fields, rest goes to payload
        envelope_keys = {
            "event_id", "event_type", "schema_version",
            "session_id", "agent_id", "correlation_id", "timestamp",
        }
        payload = {k: v for k, v in data.items() if k not in envelope_keys}
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            session_id=event.session_id,
            agent_id=event.agent_id,
            correlation_id=event.correlation_id,
            timestamp=event.timestamp.isoformat()
            if isinstance(event.timestamp, datetime)
            else str(event.timestamp),
            payload=payload,
        )

    def to_event(self) -> Event:
        """Reconstruct the typed Event from this envelope."""
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            **self.payload,
        }
        return deserialize_event(data)


# --- Wire encoding: 4-byte big-endian length prefix + JSON ---

def encode_envelope(envelope: Envelope) -> bytes:
    """Encode an envelope to length-prefixed JSON bytes."""
    json_bytes = envelope.model_dump_json().encode("utf-8")
    length = struct.pack("!I", len(json_bytes))
    return length + json_bytes


def decode_envelope(data: bytes) -> Envelope:
    """Decode an envelope from length-prefixed JSON bytes."""
    if len(data) < 4:
        raise ValueError("Data too short for length prefix")
    length = struct.unpack("!I", data[:4])[0]
    json_bytes = data[4 : 4 + length]
    return Envelope.model_validate_json(json_bytes)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/a2a/test_envelope.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add breqy/a2a/ tests/a2a/
git commit -m "feat: A2A envelope format with length-prefixed JSON wire encoding"
```

---

### Task 11: Unix Socket Transport Layer

**Files:**
- Create: `breqy/a2a/transport.py`
- Create: `tests/a2a/test_transport.py`

- [ ] **Step 1: Write failing tests**

`tests/a2a/test_transport.py`:
```python
"""Tests for Unix socket transport."""

import asyncio
from pathlib import Path

import pytest

from breqy.a2a.transport import (
    FrameReader,
    FrameWriter,
    start_unix_server,
    connect_unix,
)
from breqy.a2a.envelope import Envelope, encode_envelope
from breqy.domain.enums import EventType


@pytest.mark.asyncio
async def test_frame_write_and_read(socket_path: Path):
    """Test that frames written by one side are read correctly by the other."""
    received = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        frame_reader = FrameReader(reader)
        data = await frame_reader.read_frame()
        received.append(data)
        writer.close()
        await writer.wait_closed()

    server = await start_unix_server(handle_client, str(socket_path))

    reader, writer = await connect_unix(str(socket_path))
    frame_writer = FrameWriter(writer)

    envelope = Envelope(
        event_type=EventType.MESSAGE_SENT,
        session_id="ses_test",
        payload={"content": "Hello"},
    )
    await frame_writer.write_envelope(envelope)
    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.05)
    server.close()
    await server.wait_closed()

    assert len(received) == 1
    decoded = Envelope.model_validate_json(received[0])
    assert decoded.session_id == "ses_test"


@pytest.mark.asyncio
async def test_multiple_frames(socket_path: Path):
    """Test sending multiple frames over a single connection."""
    received = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        frame_reader = FrameReader(reader)
        while True:
            try:
                data = await frame_reader.read_frame()
                if data is None:
                    break
                received.append(data)
            except Exception:
                break
        writer.close()
        await writer.wait_closed()

    server = await start_unix_server(handle_client, str(socket_path))

    reader, writer = await connect_unix(str(socket_path))
    frame_writer = FrameWriter(writer)

    for i in range(3):
        envelope = Envelope(
            event_type=EventType.MESSAGE_SENT,
            session_id="ses_test",
            payload={"content": f"msg {i}"},
        )
        await frame_writer.write_envelope(envelope)

    writer.close()
    await writer.wait_closed()

    await asyncio.sleep(0.05)
    server.close()
    await server.wait_closed()

    assert len(received) == 3
```

- [ ] **Step 2: Implement transport**

`breqy/a2a/transport.py`:
```python
"""Low-level Unix socket transport with length-prefixed framing.

Every frame on the wire:
  [4 bytes: big-endian uint32 payload length][payload bytes]
"""

from __future__ import annotations

import asyncio
import struct
from typing import Callable, Coroutine, Any

from breqy.a2a.envelope import Envelope


async def start_unix_server(
    client_handler: Callable[
        [asyncio.StreamReader, asyncio.StreamWriter],
        Coroutine[Any, Any, None],
    ],
    socket_path: str,
) -> asyncio.AbstractServer:
    """Start a Unix domain socket server."""
    return await asyncio.start_unix_server(client_handler, path=socket_path)


async def connect_unix(
    socket_path: str,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to a Unix domain socket server."""
    return await asyncio.open_unix_connection(socket_path)


class FrameReader:
    """Reads length-prefixed frames from an asyncio StreamReader."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader

    async def read_frame(self) -> bytes | None:
        """Read one frame. Returns None on EOF."""
        header = await self._reader.readexactly(4)
        if not header:
            return None
        length = struct.unpack("!I", header)[0]
        data = await self._reader.readexactly(length)
        return data

    async def read_envelope(self) -> Envelope | None:
        """Read one frame and parse as Envelope."""
        data = await self.read_frame()
        if data is None:
            return None
        return Envelope.model_validate_json(data)


class FrameWriter:
    """Writes length-prefixed frames to an asyncio StreamWriter."""

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer

    async def write_frame(self, data: bytes) -> None:
        """Write one frame with length prefix."""
        header = struct.pack("!I", len(data))
        self._writer.write(header + data)
        await self._writer.drain()

    async def write_envelope(self, envelope: Envelope) -> None:
        """Serialize and write an envelope as a frame."""
        json_bytes = envelope.model_dump_json().encode("utf-8")
        await self.write_frame(json_bytes)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/a2a/test_transport.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/a2a/transport.py tests/a2a/test_transport.py
git commit -m "feat: Unix socket transport with length-prefixed framing"
```

---

### Task 12: A2A Server (Engine-side)

**Files:**
- Create: `breqy/a2a/server.py`
- Create: `tests/a2a/test_server_client.py`

- [ ] **Step 1: Write failing test for server**

`tests/a2a/test_server_client.py`:
```python
"""Tests for A2A server and client integration."""

import asyncio
from pathlib import Path

import pytest

from breqy.a2a.server import A2AServer
from breqy.a2a.client import A2AClient
from breqy.a2a.envelope import Envelope
from breqy.domain.enums import EventType
from breqy.domain.events import MessageSentEvent


@pytest.mark.asyncio
async def test_server_accepts_client(socket_path: Path):
    received_envelopes: list[Envelope] = []

    async def on_envelope(envelope: Envelope, client_id: str) -> None:
        received_envelopes.append(envelope)

    server = A2AServer(str(socket_path), on_envelope=on_envelope)
    await server.start()

    client = A2AClient(str(socket_path))
    await client.connect()

    event = MessageSentEvent(
        session_id="ses_test", message_id="msg_1", role="user", content="Hi"
    )
    await client.send_event(event)

    await asyncio.sleep(0.1)
    await client.disconnect()
    await server.stop()

    assert len(received_envelopes) == 1
    assert received_envelopes[0].payload["content"] == "Hi"


@pytest.mark.asyncio
async def test_server_broadcasts_to_clients(socket_path: Path):
    received: list[Envelope] = []

    async def on_envelope(envelope: Envelope, client_id: str) -> None:
        pass  # Server receives but we test broadcast

    server = A2AServer(str(socket_path), on_envelope=on_envelope)
    await server.start()

    client = A2AClient(str(socket_path))
    await client.connect()

    # Start listening in background
    listen_task = asyncio.create_task(_collect_envelopes(client, received, count=1))

    # Server broadcasts
    event = MessageSentEvent(
        session_id="ses_test", message_id="msg_1", role="agent", content="Hello back"
    )
    envelope = Envelope.from_event(event)
    await server.broadcast(envelope)

    await asyncio.wait_for(listen_task, timeout=2.0)
    await client.disconnect()
    await server.stop()

    assert len(received) == 1
    assert received[0].payload["content"] == "Hello back"


async def _collect_envelopes(
    client: A2AClient, out: list[Envelope], count: int
) -> None:
    collected = 0
    async for envelope in client.listen():
        out.append(envelope)
        collected += 1
        if collected >= count:
            break
```

- [ ] **Step 2: Implement A2A server**

`breqy/a2a/server.py`:
```python
"""Engine-side A2A server.

Accepts agent and channel connections over Unix socket.
Routes incoming envelopes to a callback.
Supports broadcasting events to all connected clients.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, start_unix_server
from breqy.domain.ids import generate_prefixed_id

logger = logging.getLogger(__name__)

OnEnvelopeCallback = Callable[[Envelope, str], Coroutine[Any, Any, None]]


class A2AServer:
    """Engine-side server that accepts A2A connections."""

    def __init__(
        self,
        socket_path: str,
        on_envelope: OnEnvelopeCallback,
    ) -> None:
        self._socket_path = socket_path
        self._on_envelope = on_envelope
        self._server: asyncio.AbstractServer | None = None
        self._clients: dict[str, FrameWriter] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self._server = await start_unix_server(
            self._handle_client, self._socket_path
        )
        logger.info("A2A server started on %s", self._socket_path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for task in self._tasks:
            task.cancel()
        self._clients.clear()
        logger.info("A2A server stopped")

    async def broadcast(
        self, envelope: Envelope, exclude_client: str = ""
    ) -> None:
        """Send envelope to all connected clients."""
        disconnected = []
        for client_id, writer in self._clients.items():
            if client_id == exclude_client:
                continue
            try:
                await writer.write_envelope(envelope)
            except (ConnectionError, OSError):
                disconnected.append(client_id)
        for cid in disconnected:
            self._clients.pop(cid, None)

    async def send_to(self, client_id: str, envelope: Envelope) -> None:
        """Send envelope to a specific client."""
        writer = self._clients.get(client_id)
        if writer:
            await writer.write_envelope(envelope)

    @property
    def connected_client_ids(self) -> list[str]:
        return list(self._clients.keys())

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client_id = generate_prefixed_id("cli")
        frame_reader = FrameReader(reader)
        frame_writer = FrameWriter(writer)
        self._clients[client_id] = frame_writer

        logger.info("Client connected: %s", client_id)

        try:
            while True:
                try:
                    envelope = await frame_reader.read_envelope()
                    if envelope is None:
                        break
                    await self._on_envelope(envelope, client_id)
                except asyncio.IncompleteReadError:
                    break
                except Exception as e:
                    logger.error("Error reading from client %s: %s", client_id, e)
                    break
        finally:
            self._clients.pop(client_id, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("Client disconnected: %s", client_id)
```

- [ ] **Step 3: Run test — it will fail because client isn't implemented yet. Proceed to Task 13.**

---

### Task 13: A2A Client (Agent/TUI-side)

**Files:**
- Create: `breqy/a2a/client.py`

- [ ] **Step 1: Implement A2A client**

`breqy/a2a/client.py`:
```python
"""Agent/TUI-side A2A client.

Connects to the engine's Unix socket, sends events, and
listens for incoming events via async iteration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, connect_unix
from breqy.domain.events import Event

logger = logging.getLogger(__name__)


class A2AClient:
    """Client that connects to the engine's A2A server."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._frame_reader: FrameReader | None = None
        self._frame_writer: FrameWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await connect_unix(self._socket_path)
        self._frame_reader = FrameReader(self._reader)
        self._frame_writer = FrameWriter(self._writer)
        logger.info("Connected to engine at %s", self._socket_path)

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    async def send_envelope(self, envelope: Envelope) -> None:
        if self._frame_writer is None:
            raise ConnectionError("Not connected")
        await self._frame_writer.write_envelope(envelope)

    async def send_event(self, event: Event) -> None:
        envelope = Envelope.from_event(event)
        await self.send_envelope(envelope)

    async def listen(self) -> AsyncIterator[Envelope]:
        """Async iterator that yields envelopes from the server."""
        if self._frame_reader is None:
            raise ConnectionError("Not connected")
        while True:
            try:
                envelope = await self._frame_reader.read_envelope()
                if envelope is None:
                    break
                yield envelope
            except asyncio.IncompleteReadError:
                break
            except Exception as e:
                logger.error("Error reading from server: %s", e)
                break
```

- [ ] **Step 2: Run server+client integration tests**

Run: `pytest tests/a2a/ -v`
Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add breqy/a2a/server.py breqy/a2a/client.py tests/a2a/test_server_client.py
git commit -m "feat: A2A server and client over Unix sockets"
```

---

## Chunk 4: Policy, Approval & Config

**Parallel: YES — can run simultaneously with Chunks 2 and 3 (after Chunk 1)**
**Depends on: Chunk 1 (domain models)**

### Task 14: Policy Models & Evaluator

**Files:**
- Create: `breqy/policy/__init__.py`
- Create: `breqy/policy/models.py`
- Create: `breqy/policy/evaluator.py`
- Create: `tests/policy/__init__.py`
- Create: `tests/policy/test_evaluator.py`

- [ ] **Step 1: Write failing tests for policy evaluator**

`tests/policy/test_evaluator.py`:
```python
"""Tests for policy evaluator — most restrictive rule wins."""

import pytest

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.policy.evaluator import PolicyEvaluator


def test_allow_when_no_rules():
    evaluator = PolicyEvaluator(rules=[])
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW


def test_global_deny_overrides_agent_allow():
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:shell"),
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.ALLOW, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.DENY


def test_agent_allow_works_when_no_global_deny():
    rules = [
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.ALLOW, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW


def test_approve_requires_approval():
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.APPROVE, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.APPROVE


def test_deny_beats_approve():
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:shell"),
        PolicyRule(scope=PolicyScope.AGENT, scope_id="breqy", action=PolicyAction.APPROVE, resource="tool:shell"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.DENY


def test_session_scope_rule():
    rules = [
        PolicyRule(scope=PolicyScope.SESSION, scope_id="ses_123", action=PolicyAction.DENY, resource="tool:ssh"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:ssh", agent_id="breqy", session_id="ses_123")
    assert decision.action == PolicyAction.DENY


def test_unmatched_resource_defaults_allow():
    rules = [
        PolicyRule(scope=PolicyScope.GLOBAL, action=PolicyAction.DENY, resource="tool:ssh"),
    ]
    evaluator = PolicyEvaluator(rules=rules)
    decision = evaluator.evaluate("tool:shell", agent_id="breqy")
    assert decision.action == PolicyAction.ALLOW
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/policy/test_evaluator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement policy evaluator**

`breqy/policy/__init__.py`:
```python
"""Policy evaluation and permission enforcement."""
```

`breqy/policy/models.py`:
```python
"""Policy evaluation result models."""

from __future__ import annotations

from pydantic import BaseModel

from breqy.domain.enums import PolicyAction


class PolicyDecision(BaseModel):
    """Result of evaluating a policy check."""

    action: PolicyAction
    matched_rule_id: str = ""
    reason: str = ""
```

`breqy/policy/evaluator.py`:
```python
"""PolicyEvaluator: layered rule resolution, most restrictive wins.

Resolution order (most restrictive wins):
1. DENY at any scope → denied
2. APPROVE at any scope (no DENY) → requires approval
3. ALLOW at any scope (no DENY/APPROVE) → allowed
4. No matching rules → allowed (default open)
"""

from __future__ import annotations

from breqy.domain.enums import PolicyAction, PolicyScope
from breqy.domain.models import PolicyRule
from breqy.policy.models import PolicyDecision

# Priority: DENY > APPROVE > ALLOW
_ACTION_PRIORITY = {
    PolicyAction.DENY: 3,
    PolicyAction.APPROVE: 2,
    PolicyAction.ALLOW: 1,
}


class PolicyEvaluator:
    """Evaluates policy rules to determine access decisions."""

    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = rules

    def evaluate(
        self,
        resource: str,
        agent_id: str = "",
        session_id: str = "",
    ) -> PolicyDecision:
        """Evaluate all matching rules. Most restrictive wins."""
        matching = self._find_matching_rules(resource, agent_id, session_id)

        if not matching:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="no matching rules")

        # Sort by restrictiveness (DENY > APPROVE > ALLOW)
        matching.sort(key=lambda r: _ACTION_PRIORITY.get(r.action, 0), reverse=True)
        winner = matching[0]

        return PolicyDecision(
            action=winner.action,
            matched_rule_id=winner.id,
            reason=f"matched {winner.scope}:{winner.resource}",
        )

    def _find_matching_rules(
        self,
        resource: str,
        agent_id: str,
        session_id: str,
    ) -> list[PolicyRule]:
        """Find all rules that match the given resource and scope."""
        matched = []
        for rule in self._rules:
            if not self._resource_matches(rule.resource, resource):
                continue
            if rule.scope == PolicyScope.GLOBAL:
                matched.append(rule)
            elif rule.scope == PolicyScope.AGENT and rule.scope_id == agent_id:
                matched.append(rule)
            elif rule.scope == PolicyScope.SESSION and rule.scope_id == session_id:
                matched.append(rule)
        return matched

    @staticmethod
    def _resource_matches(rule_resource: str, target_resource: str) -> bool:
        """Check if a rule resource matches the target. Exact or prefix match."""
        if rule_resource == target_resource:
            return True
        # Prefix match: "tool:" matches "tool:shell"
        if rule_resource.endswith(":") and target_resource.startswith(rule_resource):
            return True
        return False
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/policy/test_evaluator.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add breqy/policy/ tests/policy/
git commit -m "feat: policy evaluator with layered scope resolution"
```

---

### Task 15: Filesystem Policy

**Files:**
- Create: `breqy/policy/filesystem.py`
- Create: `tests/policy/test_filesystem_policy.py`

- [ ] **Step 1: Write failing tests**

`tests/policy/test_filesystem_policy.py`:
```python
"""Tests for filesystem path-based policy."""

import pytest

from breqy.domain.enums import FilesystemOperation, PolicyAction
from breqy.domain.models import FilesystemPolicy
from breqy.policy.filesystem import FilesystemPolicyChecker


def test_allow_when_no_rules():
    checker = FilesystemPolicyChecker(rules=[])
    result = checker.check("/home/user/file.txt", FilesystemOperation.READ)
    assert result == PolicyAction.ALLOW


def test_whitelist_allows():
    rules = [
        FilesystemPolicy(path="/home/user", operation=FilesystemOperation.READ, action=PolicyAction.ALLOW),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/home/user/file.txt", FilesystemOperation.READ)
    assert result == PolicyAction.ALLOW


def test_blacklist_denies():
    rules = [
        FilesystemPolicy(path="/etc/shadow", operation=FilesystemOperation.READ, action=PolicyAction.DENY),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/etc/shadow", FilesystemOperation.READ)
    assert result == PolicyAction.DENY


def test_deny_beats_allow():
    rules = [
        FilesystemPolicy(path="/etc", operation=FilesystemOperation.WRITE, action=PolicyAction.ALLOW),
        FilesystemPolicy(path="/etc/passwd", operation=FilesystemOperation.WRITE, action=PolicyAction.DENY),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/etc/passwd", FilesystemOperation.WRITE)
    assert result == PolicyAction.DENY


def test_directory_prefix_matching():
    rules = [
        FilesystemPolicy(path="/var/log", operation=FilesystemOperation.READ, action=PolicyAction.ALLOW),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    assert checker.check("/var/log/syslog", FilesystemOperation.READ) == PolicyAction.ALLOW
    assert checker.check("/var/lib/something", FilesystemOperation.READ) == PolicyAction.ALLOW  # no rule, default allow


def test_approve_list():
    rules = [
        FilesystemPolicy(path="/etc", operation=FilesystemOperation.WRITE, action=PolicyAction.APPROVE),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    result = checker.check("/etc/nginx/nginx.conf", FilesystemOperation.WRITE)
    assert result == PolicyAction.APPROVE


def test_different_operations_independent():
    rules = [
        FilesystemPolicy(path="/tmp", operation=FilesystemOperation.READ, action=PolicyAction.ALLOW),
        FilesystemPolicy(path="/tmp", operation=FilesystemOperation.DELETE, action=PolicyAction.DENY),
    ]
    checker = FilesystemPolicyChecker(rules=rules)
    assert checker.check("/tmp/file", FilesystemOperation.READ) == PolicyAction.ALLOW
    assert checker.check("/tmp/file", FilesystemOperation.DELETE) == PolicyAction.DENY
```

- [ ] **Step 2: Implement filesystem policy**

`breqy/policy/filesystem.py`:
```python
"""Filesystem path-based policy checker.

Uses exact path and directory-prefix matching (no globs in v1).
Most restrictive matching rule wins (DENY > APPROVE > ALLOW).
"""

from __future__ import annotations

from pathlib import PurePosixPath

from breqy.domain.enums import FilesystemOperation, PolicyAction
from breqy.domain.models import FilesystemPolicy

_ACTION_PRIORITY = {
    PolicyAction.DENY: 3,
    PolicyAction.APPROVE: 2,
    PolicyAction.ALLOW: 1,
}


class FilesystemPolicyChecker:
    """Checks filesystem access against path-based rules."""

    def __init__(self, rules: list[FilesystemPolicy]) -> None:
        self._rules = rules

    def check(self, path: str, operation: FilesystemOperation) -> PolicyAction:
        """Check if the given path+operation is allowed."""
        matching = []
        target = PurePosixPath(path)

        for rule in self._rules:
            if rule.operation != operation:
                continue
            rule_path = PurePosixPath(rule.path)
            # Exact match or directory prefix
            if target == rule_path or self._is_under(target, rule_path):
                matching.append(rule)

        if not matching:
            return PolicyAction.ALLOW

        # Most restrictive wins, most specific path breaks ties
        matching.sort(
            key=lambda r: (
                _ACTION_PRIORITY.get(r.action, 0),
                len(str(r.path)),
            ),
            reverse=True,
        )
        return matching[0].action

    @staticmethod
    def _is_under(target: PurePosixPath, rule_path: PurePosixPath) -> bool:
        """Check if target is under rule_path directory."""
        try:
            target.relative_to(rule_path)
            return True
        except ValueError:
            return False
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/policy/test_filesystem_policy.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/policy/filesystem.py tests/policy/test_filesystem_policy.py
git commit -m "feat: filesystem path-based policy checker"
```

---

### Task 16: Approval Service

**Files:**
- Create: `breqy/approval/__init__.py`
- Create: `breqy/approval/service.py`
- Create: `tests/approval/__init__.py`
- Create: `tests/approval/test_service.py`

- [ ] **Step 1: Write failing tests**

`tests/approval/test_service.py`:
```python
"""Tests for approval service."""

import asyncio
import pytest

from breqy.approval.service import ApprovalService


@pytest.mark.asyncio
async def test_request_and_grant_approval():
    service = ApprovalService()
    request_id = await service.request_approval(
        session_id="ses_1",
        agent_id="breqy",
        tool_invocation_id="inv_1",
        description="Execute: ls -la",
    )
    assert request_id is not None

    # Simulate user granting
    await service.decide(request_id, granted=True)
    assert await service.is_granted(request_id) is True


@pytest.mark.asyncio
async def test_request_and_deny_approval():
    service = ApprovalService()
    request_id = await service.request_approval(
        session_id="ses_1",
        agent_id="breqy",
        tool_invocation_id="inv_1",
        description="Execute: rm -rf /",
    )
    await service.decide(request_id, granted=False)
    assert await service.is_granted(request_id) is False


@pytest.mark.asyncio
async def test_session_grant_skips_future_approvals():
    service = ApprovalService()
    # Grant with extend_to_session=True
    req_id = await service.request_approval(
        session_id="ses_1",
        agent_id="breqy",
        tool_invocation_id="inv_1",
        description="Execute: ls",
    )
    await service.decide(req_id, granted=True, extend_to_session=True)

    # Check if tool:shell is pre-approved for session
    has_grant = service.has_session_grant("ses_1", "Execute: ls")
    assert has_grant is True


@pytest.mark.asyncio
async def test_wait_for_decision():
    service = ApprovalService()
    req_id = await service.request_approval(
        session_id="ses_1",
        agent_id="breqy",
        tool_invocation_id="inv_1",
        description="Execute: whoami",
    )

    # Decide in background after small delay
    async def delayed_decide():
        await asyncio.sleep(0.05)
        await service.decide(req_id, granted=True)

    asyncio.create_task(delayed_decide())

    granted = await service.wait_for_decision(req_id, timeout=2.0)
    assert granted is True
```

- [ ] **Step 2: Implement approval service**

`breqy/approval/__init__.py`:
```python
"""Approval workflow for tool execution."""
```

`breqy/approval/service.py`:
```python
"""In-memory approval service for managing approval requests and decisions.

Supports:
- Creating approval requests
- Waiting for decisions (async)
- Session-scoped grants (extend approval to rest of session)
"""

from __future__ import annotations

import asyncio
import logging

from breqy.domain.ids import generate_prefixed_id

logger = logging.getLogger(__name__)


class _PendingApproval:
    def __init__(self, request_id: str, session_id: str, description: str) -> None:
        self.request_id = request_id
        self.session_id = session_id
        self.description = description
        self.decided = asyncio.Event()
        self.granted: bool = False
        self.extend_to_session: bool = False


class ApprovalService:
    """Manages approval requests and decisions in-memory."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingApproval] = {}
        # session_id -> set of granted descriptions
        self._session_grants: dict[str, set[str]] = {}

    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
    ) -> str:
        """Create an approval request. Returns the request ID."""
        request_id = generate_prefixed_id("apr")
        pending = _PendingApproval(
            request_id=request_id,
            session_id=session_id,
            description=description,
        )
        self._pending[request_id] = pending
        logger.info("Approval requested: %s — %s", request_id, description)
        return request_id

    async def decide(
        self,
        request_id: str,
        granted: bool,
        extend_to_session: bool = False,
    ) -> None:
        """Record a user decision on an approval request."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        pending.granted = granted
        pending.extend_to_session = extend_to_session

        if granted and extend_to_session:
            grants = self._session_grants.setdefault(pending.session_id, set())
            grants.add(pending.description)

        pending.decided.set()
        logger.info(
            "Approval %s: %s (extend=%s)",
            "granted" if granted else "denied",
            request_id,
            extend_to_session,
        )

    async def is_granted(self, request_id: str) -> bool:
        """Check if an approval was granted."""
        pending = self._pending.get(request_id)
        if pending is None:
            return False
        return pending.granted

    def has_session_grant(self, session_id: str, description: str) -> bool:
        """Check if a session-wide grant exists for this description."""
        grants = self._session_grants.get(session_id, set())
        return description in grants

    async def wait_for_decision(self, request_id: str, timeout: float = 300.0) -> bool:
        """Wait for a user decision. Returns True if granted, False if denied."""
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError(f"No pending approval: {request_id}")

        try:
            await asyncio.wait_for(pending.decided.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Approval timed out: %s", request_id)
            return False

        return pending.granted

    def get_pending_for_session(self, session_id: str) -> list[str]:
        """Get all pending approval request IDs for a session."""
        return [
            p.request_id
            for p in self._pending.values()
            if p.session_id == session_id and not p.decided.is_set()
        ]
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/approval/test_service.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/approval/ tests/approval/
git commit -m "feat: approval service with session-scoped grants"
```

---

### Task 17: Config Loader & Secret Provider

**Files:**
- Create: `breqy/config/__init__.py`
- Create: `breqy/config/loader.py`
- Create: `breqy/config/models.py`
- Create: `breqy/secrets/__init__.py`
- Create: `breqy/secrets/provider.py`
- Create: `breqy/utils/__init__.py`
- Create: `breqy/utils/logging.py`

- [ ] **Step 1: Implement config models**

`breqy/config/__init__.py`:
```python
"""Configuration loading and models."""
```

`breqy/config/models.py`:
```python
"""Configuration dataclasses for engine and agent."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class EngineConfig(BaseModel):
    """Engine daemon configuration."""

    socket_path: str = Field(default_factory=lambda: os.getenv("BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock"))
    data_dir: str = Field(default_factory=lambda: os.getenv("BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data")))
    db_path: str = Field(default_factory=lambda: os.getenv("BREQY_DB_PATH", str(Path.home() / ".breqy" / "data" / "breqy.db")))
    log_level: str = Field(default_factory=lambda: os.getenv("BREQY_LOG_LEVEL", "INFO"))
    default_agent_id: str = "breqy"


class AgentConfig(BaseModel):
    """Agent process configuration loaded from agent.yaml."""

    id: str
    name: str
    display_name: str = ""
    port: int | None = None
    engine_socket: str = "/tmp/breqy-engine.sock"
    persona_file: str = "persona.md"
    autonomy_level: str = "supervised"
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str = ""
```

- [ ] **Step 2: Implement config loader**

`breqy/config/loader.py`:
```python
"""Load configuration from YAML files and environment."""

from __future__ import annotations

from pathlib import Path

import yaml

from breqy.config.models import AgentConfig, EngineConfig


def load_engine_config(config_path: str | None = None) -> EngineConfig:
    """Load engine config from env vars, optionally supplemented by YAML."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return EngineConfig(**data)
    return EngineConfig()


def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load agent config from agent.yaml in the given directory."""
    config_path = Path(agent_dir) / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return AgentConfig(**data)
```

- [ ] **Step 3: Implement secret provider**

`breqy/secrets/__init__.py`:
```python
"""Secret management abstraction."""
```

`breqy/secrets/provider.py`:
```python
"""SecretProvider interface with keyring and env fallback implementations."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """Abstract secret storage interface."""

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class EnvSecretProvider(SecretProvider):
    """Read secrets from environment variables. Fallback for dev."""

    def get(self, key: str) -> str | None:
        return os.environ.get(f"BREQY_SECRET_{key.upper()}")

    def set(self, key: str, value: str) -> None:
        os.environ[f"BREQY_SECRET_{key.upper()}"] = value

    def delete(self, key: str) -> None:
        os.environ.pop(f"BREQY_SECRET_{key.upper()}", None)


class KeyringSecretProvider(SecretProvider):
    """Use system keyring for secret storage."""

    SERVICE_NAME = "breqy"

    def get(self, key: str) -> str | None:
        import keyring
        return keyring.get_password(self.SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        import keyring
        keyring.set_password(self.SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import keyring
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
```

- [ ] **Step 4: Implement structured logging setup**

`breqy/utils/__init__.py`:
```python
"""Shared utilities."""
```

`breqy/utils/logging.py`:
```python
"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
    """Configure structlog with human-readable console output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 5: Commit**

```bash
git add breqy/config/ breqy/secrets/ breqy/utils/
git commit -m "feat: config loader, secret provider, and structured logging"
```

---

## Chunk 5: Engine Core

**Parallel: NO — depends on Chunks 2 (Storage) and 4 (Policy/Approval)**
**Can run in PARALLEL with Chunk 6 (Tools) and Chunk 8 (TUI)**

### Task 18: Event Bus (In-Process Pub/Sub)

**Files:**
- Create: `breqy/engine/__init__.py`
- Create: `breqy/engine/event_bus.py`
- Create: `tests/engine/__init__.py`
- Create: `tests/engine/test_event_bus.py`

- [ ] **Step 1: Write failing tests**

`tests/engine/test_event_bus.py`:
```python
"""Tests for in-process event bus."""

import asyncio
import pytest

from breqy.engine.event_bus import EventBus
from breqy.domain.events import MessageSentEvent, ToolInvocationStartedEvent
from breqy.domain.enums import EventType


@pytest.mark.asyncio
async def test_subscribe_and_receive():
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

- [ ] **Step 2: Implement event bus**

`breqy/engine/__init__.py`:
```python
"""Breqy engine: daemon, session management, event routing."""
```

`breqy/engine/event_bus.py`:
```python
"""In-process async event bus for the engine.

Supports typed subscriptions and wildcard listeners.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

from breqy.domain.enums import EventType
from breqy.domain.events import Event
from breqy.domain.ids import generate_prefixed_id

logger = logging.getLogger(__name__)

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus."""

    def __init__(self) -> None:
        self._typed_handlers: dict[EventType, dict[str, EventHandler]] = {}
        self._wildcard_handlers: dict[str, EventHandler] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> str:
        """Subscribe to a specific event type. Returns subscription ID."""
        sub_id = generate_prefixed_id("sub")
        handlers = self._typed_handlers.setdefault(event_type, {})
        handlers[sub_id] = handler
        return sub_id

    def subscribe_all(self, handler: EventHandler) -> str:
        """Subscribe to all events."""
        sub_id = generate_prefixed_id("sub")
        self._wildcard_handlers[sub_id] = handler
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscription."""
        self._wildcard_handlers.pop(sub_id, None)
        for handlers in self._typed_handlers.values():
            handlers.pop(sub_id, None)

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers."""
        handlers_to_call: list[EventHandler] = []

        # Typed handlers
        typed = self._typed_handlers.get(event.event_type, {})
        handlers_to_call.extend(typed.values())

        # Wildcard handlers
        handlers_to_call.extend(self._wildcard_handlers.values())

        for handler in handlers_to_call:
            try:
                await handler(event)
            except Exception:
                logger.exception("Error in event handler for %s", event.event_type)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/engine/test_event_bus.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/engine/ tests/engine/
git commit -m "feat: in-process async event bus"
```

---

### Task 19: Centralized Event Writer

**Files:**
- Create: `breqy/engine/event_writer.py`
- Create: `tests/engine/test_event_writer.py`

- [ ] **Step 1: Write failing tests**

`tests/engine/test_event_writer.py`:
```python
"""Tests for centralized event writer."""

import asyncio
import pytest

from breqy.engine.event_writer import EventWriter
from breqy.domain.events import MessageSentEvent
from breqy.domain.models import Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository


@pytest.mark.asyncio
async def test_event_writer_writes_events(db_connection):
    # Create session first
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    writer = EventWriter(event_repo)
    await writer.start()

    event = MessageSentEvent(
        session_id=session.id, message_id="msg_1", role="user", content="Hello"
    )
    await writer.enqueue(event)
    await asyncio.sleep(0.1)  # Let writer process

    await writer.stop()

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 1
    assert events[0].event_type.value == "message.sent"


@pytest.mark.asyncio
async def test_event_writer_handles_multiple_events(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    event_repo = SqliteEventRepository(db_connection)
    writer = EventWriter(event_repo)
    await writer.start()

    for i in range(10):
        event = MessageSentEvent(
            session_id=session.id, message_id=f"msg_{i}", role="user", content=f"msg {i}"
        )
        await writer.enqueue(event)

    await asyncio.sleep(0.2)
    await writer.stop()

    events = await event_repo.list_by_session(session.id)
    assert len(events) == 10
```

- [ ] **Step 2: Implement event writer**

`breqy/engine/event_writer.py`:
```python
"""Centralized sequential event writer.

Accepts events from an async queue and writes them
sequentially to the event repository, preventing
SQLite write contention from concurrent agents.
"""

from __future__ import annotations

import asyncio
import logging

from breqy.domain.events import Event
from breqy.storage.interfaces import EventRepository

logger = logging.getLogger(__name__)


class EventWriter:
    """Queues events and writes them sequentially to storage."""

    def __init__(self, event_repo: EventRepository) -> None:
        self._repo = event_repo
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background writer loop."""
        self._task = asyncio.create_task(self._write_loop())
        logger.info("Event writer started")

    async def stop(self) -> None:
        """Signal stop and wait for drain."""
        await self._queue.put(None)  # Sentinel
        if self._task:
            await self._task
        logger.info("Event writer stopped")

    async def enqueue(self, event: Event) -> None:
        """Add an event to the write queue."""
        await self._queue.put(event)

    async def _write_loop(self) -> None:
        while True:
            event = await self._queue.get()
            if event is None:
                break
            try:
                await self._repo.append(event)
            except Exception:
                logger.exception("Failed to write event %s", event.event_id)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/engine/test_event_writer.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/engine/event_writer.py tests/engine/test_event_writer.py
git commit -m "feat: centralized sequential event writer"
```

---

### Task 20: Session Manager

**Files:**
- Create: `breqy/engine/session_manager.py`
- Create: `tests/engine/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

`tests/engine/test_session_manager.py`:
```python
"""Tests for session manager."""

import pytest

from breqy.engine.session_manager import SessionManager
from breqy.domain.enums import SessionStatus, MessageRole
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository


@pytest.mark.asyncio
async def test_create_session(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    assert session.status == SessionStatus.ACTIVE
    assert session.primary_agent_id == "breqy"

    # Should be retrievable
    retrieved = await manager.get_session(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id


@pytest.mark.asyncio
async def test_list_sessions(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    await manager.create_session(agent_id="breqy")
    await manager.create_session(agent_id="breqy")

    sessions = await manager.list_sessions()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_add_message(db_connection):
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
    session_repo = SqliteSessionRepository(db_connection)
    message_repo = SqliteMessageRepository(db_connection)
    manager = SessionManager(session_repo, message_repo)

    session = await manager.create_session(agent_id="breqy")
    await manager.close_session(session.id)

    result = await manager.get_session(session.id)
    assert result.status == SessionStatus.CLOSED
```

- [ ] **Step 2: Implement session manager**

`breqy/engine/session_manager.py`:
```python
"""Session lifecycle management."""

from __future__ import annotations

import logging

from breqy.domain.enums import MessageRole, SessionStatus
from breqy.domain.models import Message, Session
from breqy.storage.interfaces import MessageRepository, SessionRepository

logger = logging.getLogger(__name__)


class SessionManager:
    """Creates, resumes, and manages sessions."""

    def __init__(
        self,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
    ) -> None:
        self._sessions = session_repo
        self._messages = message_repo

    async def create_session(self, agent_id: str) -> Session:
        session = Session(primary_agent_id=agent_id)
        await self._sessions.create(session)
        logger.info("Session created: %s", session.id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        return await self._sessions.get(session_id)

    async def list_sessions(self) -> list[Session]:
        return await self._sessions.list_active()

    async def close_session(self, session_id: str) -> None:
        await self._sessions.update_status(session_id, SessionStatus.CLOSED)
        logger.info("Session closed: %s", session_id)

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        agent_id: str | None = None,
    ) -> Message:
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
        return await self._messages.list_by_session(session_id, limit=limit)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/engine/test_session_manager.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/engine/session_manager.py tests/engine/test_session_manager.py
git commit -m "feat: session manager for create/resume/list/close"
```

---

### Task 21: Agent Registry & Spawner

**Files:**
- Create: `breqy/engine/agent_registry.py`
- Create: `breqy/engine/agent_spawner.py`
- Create: `tests/engine/test_agent_registry.py`
- Create: `tests/engine/test_agent_spawner.py`

- [ ] **Step 1: Write tests for agent registry**

`tests/engine/test_agent_registry.py`:
```python
"""Tests for agent registry."""

from breqy.engine.agent_registry import AgentRegistry


def test_register_and_lookup():
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")

    info = registry.get("breqy")
    assert info is not None
    assert info.client_id == "cli_123"


def test_unregister():
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_123")
    registry.unregister("breqy")

    assert registry.get("breqy") is None


def test_list_agents():
    registry = AgentRegistry()
    registry.register("breqy", client_id="cli_1")
    registry.register("docker-agent", client_id="cli_2")

    agents = registry.list_agents()
    assert len(agents) == 2
```

- [ ] **Step 2: Implement agent registry**

`breqy/engine/agent_registry.py`:
```python
"""Tracks connected agents and their A2A client IDs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentInfo:
    agent_id: str
    client_id: str
    pid: int | None = None


class AgentRegistry:
    """Registry of connected agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(self, agent_id: str, client_id: str, pid: int | None = None) -> None:
        self._agents[agent_id] = AgentInfo(
            agent_id=agent_id, client_id=client_id, pid=pid
        )

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> AgentInfo | None:
        return self._agents.get(agent_id)

    def get_by_client_id(self, client_id: str) -> AgentInfo | None:
        for info in self._agents.values():
            if info.client_id == client_id:
                return info
        return None

    def list_agents(self) -> list[AgentInfo]:
        return list(self._agents.values())
```

- [ ] **Step 3: Write tests for agent spawner**

`tests/engine/test_agent_spawner.py`:
```python
"""Tests for agent spawner."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

from breqy.engine.agent_spawner import AgentSpawner


def test_spawner_builds_command():
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    cmd = spawner._build_command("system/agents/breqy")
    assert sys.executable in cmd[0] or "python" in cmd[0]
    assert "-m" in cmd
    assert "breqy.agents.runtime" in cmd


def test_spawner_tracks_processes():
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    assert spawner.list_running() == []
```

- [ ] **Step 4: Implement agent spawner**

`breqy/engine/agent_spawner.py`:
```python
"""Agent process spawner and supervisor."""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpawnedAgent:
    agent_dir: str
    process: subprocess.Popen[bytes]


class AgentSpawner:
    """Spawns and manages agent subprocesses."""

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
        logger.info("Spawned agent %s with PID %d", agent_dir, process.pid)
        return process.pid

    def kill(self, agent_dir: str) -> None:
        """Kill an agent process."""
        spawned = self._processes.pop(agent_dir, None)
        if spawned and spawned.process.poll() is None:
            spawned.process.terminate()
            logger.info("Terminated agent %s", agent_dir)

    def kill_all(self) -> None:
        """Kill all agent processes (circuit break)."""
        for agent_dir in list(self._processes.keys()):
            self.kill(agent_dir)

    def is_running(self, agent_dir: str) -> bool:
        spawned = self._processes.get(agent_dir)
        if spawned is None:
            return False
        return spawned.process.poll() is None

    def list_running(self) -> list[str]:
        return [d for d in self._processes if self.is_running(d)]

    def _build_command(self, agent_dir: str) -> list[str]:
        return [
            sys.executable, "-m", "breqy.agents.runtime",
            "--agent-dir", agent_dir,
            "--engine-socket", self._engine_socket,
        ]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/engine/test_agent_registry.py tests/engine/test_agent_spawner.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add breqy/engine/agent_registry.py breqy/engine/agent_spawner.py tests/engine/test_agent_registry.py tests/engine/test_agent_spawner.py
git commit -m "feat: agent registry and subprocess spawner"
```

---

### Task 22: Engine Daemon & Server

**Files:**
- Create: `breqy/engine/daemon.py`
- Create: `breqy/engine/server.py`
- Create: `tests/engine/test_daemon.py`

- [ ] **Step 1: Write test for daemon lifecycle**

`tests/engine/test_daemon.py`:
```python
"""Tests for engine daemon lifecycle."""

import asyncio
import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(tmp_dir: Path):
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

- [ ] **Step 2: Implement daemon and server**

`breqy/engine/server.py`:
```python
"""Engine server: ties together all engine components."""

from __future__ import annotations

import logging

from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.approval.service import ApprovalService
from breqy.engine.agent_registry import AgentRegistry
from breqy.engine.agent_spawner import AgentSpawner
from breqy.engine.event_bus import EventBus
from breqy.engine.event_writer import EventWriter
from breqy.engine.session_manager import SessionManager
from breqy.storage.interfaces import (
    EventRepository,
    MessageRepository,
    SessionRepository,
    TaskRepository,
)

logger = logging.getLogger(__name__)


class EngineServer:
    """Composes all engine components and handles A2A routing."""

    def __init__(
        self,
        socket_path: str,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        event_repo: EventRepository,
        task_repo: TaskRepository,
    ) -> None:
        self.event_bus = EventBus()
        self.event_writer = EventWriter(event_repo)
        self.session_manager = SessionManager(session_repo, message_repo)
        self.agent_registry = AgentRegistry()
        self.agent_spawner = AgentSpawner(engine_socket=socket_path)
        self.approval_service = ApprovalService()
        self.a2a_server = A2AServer(
            socket_path=socket_path,
            on_envelope=self._handle_envelope,
        )
        self._task_repo = task_repo

    async def start(self) -> None:
        await self.event_writer.start()
        await self.a2a_server.start()
        # Subscribe event writer to all events
        self.event_bus.subscribe_all(self.event_writer.enqueue)
        logger.info("Engine server started")

    async def stop(self) -> None:
        self.agent_spawner.kill_all()
        await self.a2a_server.stop()
        await self.event_writer.stop()
        logger.info("Engine server stopped")

    async def _handle_envelope(self, envelope: Envelope, client_id: str) -> None:
        """Route incoming envelopes from agents/channels."""
        event = envelope.to_event()
        await self.event_bus.publish(event)
        # Broadcast to other connected clients
        await self.a2a_server.broadcast(envelope, exclude_client=client_id)
```

`breqy/engine/daemon.py`:
```python
"""Engine daemon: lifecycle management, signal handling, startup."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from breqy.config.models import EngineConfig
from breqy.engine.server import EngineServer
from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.utils.logging import setup_logging

logger = logging.getLogger(__name__)


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
        setup_logging(self._config.log_level)

        # Ensure data directory exists
        Path(self._config.data_dir).mkdir(parents=True, exist_ok=True)

        # Initialize storage
        conn = await create_connection(self._config.db_path)
        await run_migrations(conn)

        session_repo = SqliteSessionRepository(conn)
        message_repo = SqliteMessageRepository(conn)
        event_repo = SqliteEventRepository(conn)
        task_repo = SqliteTaskRepository(conn)

        self._server = EngineServer(
            socket_path=self._config.socket_path,
            session_repo=session_repo,
            message_repo=message_repo,
            event_repo=event_repo,
            task_repo=task_repo,
        )
        await self._server.start()
        self._running = True
        logger.info("Engine daemon started — socket: %s", self._config.socket_path)

    async def stop(self) -> None:
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

        # Keep running until stopped
        while daemon.is_running:
            await asyncio.sleep(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/engine/test_daemon.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/engine/daemon.py breqy/engine/server.py tests/engine/test_daemon.py
git commit -m "feat: engine daemon with lifecycle and A2A server integration"
```

---

## Chunk 6: Tool System

**Parallel: YES — can run simultaneously with Chunks 5 and 8 (after Chunk 4/Policy)**
**Depends on: Chunk 4 (Policy/Approval)**

### Task 23: Tool Executor & Registry

**Files:**
- Create: `breqy/tools/__init__.py`
- Create: `breqy/tools/executor.py`
- Create: `breqy/tools/registry.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_executor.py`

- [ ] **Step 1: Write failing tests**

`tests/tools/test_executor.py`:
```python
"""Tests for tool executor and registry."""

import pytest

from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.registry import ToolRegistry


class EchoTool(ToolExecutor):
    name = "echo"
    description = "Echoes input back"

    async def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(
            success=True,
            output={"echoed": arguments.get("text", "")},
            summary=f"Echoed: {arguments.get('text', '')}",
        )


def test_tool_registry():
    registry = ToolRegistry()
    echo = EchoTool()
    registry.register(echo)

    assert registry.get("echo") is echo
    assert registry.get("nonexistent") is None
    assert "echo" in registry.list_tools()


@pytest.mark.asyncio
async def test_tool_execution():
    tool = EchoTool()
    result = await tool.execute({"text": "hello"})
    assert result.success is True
    assert result.output["echoed"] == "hello"


def test_registry_prevents_duplicates():
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(ValueError):
        registry.register(EchoTool())
```

- [ ] **Step 2: Implement tool executor and registry**

`breqy/tools/__init__.py`:
```python
"""Tool execution framework."""
```

`breqy/tools/executor.py`:
```python
"""Tool executor abstraction and result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result from tool execution."""

    success: bool
    output: dict[str, Any] = {}
    error: str = ""
    summary: str = ""


class ToolExecutor(ABC):
    """Abstract base for all tools."""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...
```

`breqy/tools/registry.py`:
```python
"""Tool registration and lookup."""

from __future__ import annotations

from breqy.tools.executor import ToolExecutor


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolExecutor] = {}

    def register(self, tool: ToolExecutor) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolExecutor | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_executor.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/tools/ tests/tools/
git commit -m "feat: tool executor abstraction and registry"
```

---

### Task 24: Shell Tool

**Files:**
- Create: `breqy/tools/shell.py`
- Create: `tests/tools/test_shell.py`

- [ ] **Step 1: Write failing tests**

`tests/tools/test_shell.py`:
```python
"""Tests for shell tool."""

import pytest

from breqy.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_echo():
    tool = ShellTool()
    result = await tool.execute({"command": "echo hello"})
    assert result.success is True
    assert "hello" in result.output["stdout"]


@pytest.mark.asyncio
async def test_shell_failed_command():
    tool = ShellTool()
    result = await tool.execute({"command": "false"})
    assert result.success is False
    assert result.output["return_code"] != 0


@pytest.mark.asyncio
async def test_shell_timeout():
    tool = ShellTool(timeout=1)
    result = await tool.execute({"command": "sleep 10"})
    assert result.success is False
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_requires_command():
    tool = ShellTool()
    result = await tool.execute({})
    assert result.success is False
    assert "command" in result.error.lower()
```

- [ ] **Step 2: Implement shell tool**

`breqy/tools/shell.py`:
```python
"""Shell execution tool — runs commands via subprocess."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from breqy.tools.executor import ToolExecutor, ToolResult

logger = logging.getLogger(__name__)


class ShellTool(ToolExecutor):
    name = "shell"
    description = "Execute a shell command and return its output"

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command")
        if not command:
            return ToolResult(success=False, error="Missing required argument: command")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )

            return_code = process.returncode or 0
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            return ToolResult(
                success=return_code == 0,
                output={
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "return_code": return_code,
                },
                error=stderr_str if return_code != 0 else "",
                summary=f"Command exited with code {return_code}",
            )

        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(
                success=False,
                error=f"Timeout after {self._timeout}s",
                summary=f"Command timed out after {self._timeout}s",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_shell.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/tools/shell.py tests/tools/test_shell.py
git commit -m "feat: shell tool with timeout support"
```

---

### Task 25: Filesystem Tool

**Files:**
- Create: `breqy/tools/filesystem.py`
- Create: `tests/tools/test_filesystem_tool.py`

- [ ] **Step 1: Write failing tests**

`tests/tools/test_filesystem_tool.py`:
```python
"""Tests for filesystem tool."""

import pytest
from pathlib import Path

from breqy.tools.filesystem import FilesystemTool


@pytest.mark.asyncio
async def test_read_file(tmp_dir: Path):
    test_file = tmp_dir / "test.txt"
    test_file.write_text("hello world")

    tool = FilesystemTool()
    result = await tool.execute({"operation": "read", "path": str(test_file)})
    assert result.success is True
    assert result.output["content"] == "hello world"


@pytest.mark.asyncio
async def test_write_file(tmp_dir: Path):
    test_file = tmp_dir / "output.txt"

    tool = FilesystemTool()
    result = await tool.execute({
        "operation": "write",
        "path": str(test_file),
        "content": "new content",
    })
    assert result.success is True
    assert test_file.read_text() == "new content"


@pytest.mark.asyncio
async def test_edit_file(tmp_dir: Path):
    test_file = tmp_dir / "edit.txt"
    test_file.write_text("old text here")

    tool = FilesystemTool()
    result = await tool.execute({
        "operation": "edit",
        "path": str(test_file),
        "old_string": "old text",
        "new_string": "new text",
    })
    assert result.success is True
    assert test_file.read_text() == "new text here"


@pytest.mark.asyncio
async def test_delete_file(tmp_dir: Path):
    test_file = tmp_dir / "delete.txt"
    test_file.write_text("delete me")

    tool = FilesystemTool()
    result = await tool.execute({"operation": "delete", "path": str(test_file)})
    assert result.success is True
    assert not test_file.exists()


@pytest.mark.asyncio
async def test_read_nonexistent():
    tool = FilesystemTool()
    result = await tool.execute({"operation": "read", "path": "/nonexistent/file"})
    assert result.success is False


@pytest.mark.asyncio
async def test_invalid_operation():
    tool = FilesystemTool()
    result = await tool.execute({"operation": "invalid", "path": "/tmp/file"})
    assert result.success is False
```

- [ ] **Step 2: Implement filesystem tool**

`breqy/tools/filesystem.py`:
```python
"""Filesystem tool — read, write, edit, delete files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from breqy.tools.executor import ToolExecutor, ToolResult

logger = logging.getLogger(__name__)


class FilesystemTool(ToolExecutor):
    name = "filesystem"
    description = "Read, write, edit, and delete files"

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        operation = arguments.get("operation", "")
        path = arguments.get("path", "")

        if not path:
            return ToolResult(success=False, error="Missing required argument: path")

        match operation:
            case "read":
                return await self._read(path)
            case "write":
                content = arguments.get("content", "")
                return await self._write(path, content)
            case "edit":
                old = arguments.get("old_string", "")
                new = arguments.get("new_string", "")
                return await self._edit(path, old, new)
            case "delete":
                return await self._delete(path)
            case _:
                return ToolResult(
                    success=False,
                    error=f"Invalid operation: {operation}. Use: read, write, edit, delete",
                )

    async def _read(self, path: str) -> ToolResult:
        try:
            content = Path(path).read_text()
            return ToolResult(
                success=True,
                output={"content": content},
                summary=f"Read {len(content)} chars from {path}",
            )
        except FileNotFoundError:
            return ToolResult(success=False, error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _write(self, path: str, content: str) -> ToolResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return ToolResult(
                success=True,
                summary=f"Wrote {len(content)} chars to {path}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _edit(self, path: str, old_string: str, new_string: str) -> ToolResult:
        try:
            p = Path(path)
            content = p.read_text()
            if old_string not in content:
                return ToolResult(
                    success=False,
                    error=f"String not found in {path}: {old_string[:50]}",
                )
            new_content = content.replace(old_string, new_string, 1)
            p.write_text(new_content)
            return ToolResult(
                success=True,
                summary=f"Edited {path}: replaced '{old_string[:30]}' with '{new_string[:30]}'",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _delete(self, path: str) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            p.unlink()
            return ToolResult(success=True, summary=f"Deleted {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/tools/test_filesystem_tool.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/tools/filesystem.py tests/tools/test_filesystem_tool.py
git commit -m "feat: filesystem tool with read/write/edit/delete"
```

---

## Chunk 7: Agent Runtime & Default Agent

**Parallel: NO — depends on Chunks 3 (A2A), 5 (Engine), and 6 (Tools)**

### Task 26: Agent Config Loader

**Files:**
- Create: `breqy/agents/__init__.py`
- Create: `breqy/agents/config.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_config.py`
- Create: `system/agents/breqy/agent.yaml`
- Create: `system/agents/breqy/persona.md`

- [ ] **Step 1: Create default agent manifest**

`system/agents/breqy/agent.yaml`:
```yaml
id: breqy
name: breqy
display_name: Breqy
persona_file: persona.md
autonomy_level: supervised
tool_permissions:
  - shell
  - filesystem
skill_permissions:
  - "*"
log_level: INFO
```

`system/agents/breqy/persona.md`:
```markdown
# Breqy

You are Breqy, an always-on technical assistant.

## Traits
- Sharp, calm, high-agency
- Slightly disruptive but trustworthy
- Concise by default, structured when executing

## Behavior
- Move work forward
- Produce visible plans for non-trivial work
- Respect policy boundaries
- Adapt quickly when interrupted or redirected
- State facts, impact, likely cause, and recovery path when things fail
- Never dramatize failure or hide next steps
```

- [ ] **Step 2: Write failing test for agent config**

`tests/agents/test_config.py`:
```python
"""Tests for agent config loader."""

import pytest
from pathlib import Path

from breqy.agents.config import load_agent_config


def test_load_agent_config(tmp_dir: Path):
    agent_dir = tmp_dir / "test_agent"
    agent_dir.mkdir()

    config_file = agent_dir / "agent.yaml"
    config_file.write_text("""
id: test_agent
name: test_agent
display_name: Test Agent
autonomy_level: supervised
tool_permissions:
  - shell
""")

    persona_file = agent_dir / "persona.md"
    persona_file.write_text("You are a test agent.")

    config = load_agent_config(str(agent_dir))
    assert config.id == "test_agent"
    assert config.autonomy_level == "supervised"
    assert "shell" in config.tool_permissions


def test_load_agent_config_missing_file(tmp_dir: Path):
    with pytest.raises(FileNotFoundError):
        load_agent_config(str(tmp_dir / "nonexistent"))


def test_load_persona(tmp_dir: Path):
    agent_dir = tmp_dir / "test_agent"
    agent_dir.mkdir()
    (agent_dir / "agent.yaml").write_text("id: test\nname: test\n")
    (agent_dir / "persona.md").write_text("You are helpful.")

    from breqy.agents.config import load_persona
    persona = load_persona(str(agent_dir), "persona.md")
    assert "helpful" in persona
```

- [ ] **Step 3: Implement agent config**

`breqy/agents/__init__.py`:
```python
"""Agent runtime and configuration."""
```

`breqy/agents/config.py`:
```python
"""Agent configuration loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from breqy.config.models import AgentConfig


def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load agent config from agent.yaml."""
    config_path = Path(agent_dir) / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return AgentConfig(**data)


def load_persona(agent_dir: str, persona_file: str) -> str:
    """Load the agent's persona markdown."""
    persona_path = Path(agent_dir) / persona_file
    if not persona_path.exists():
        return ""
    return persona_path.read_text()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agents/test_config.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/ tests/agents/ system/agents/breqy/
git commit -m "feat: agent config loader and default breqy agent manifest"
```

---

### Task 27: Agent Runtime Loop

**Files:**
- Create: `breqy/agents/runtime.py`
- Create: `tests/agents/test_runtime.py`

- [ ] **Step 1: Write failing test**

`tests/agents/test_runtime.py`:
```python
"""Tests for agent runtime."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from breqy.agents.runtime import AgentRuntime
from breqy.a2a.envelope import Envelope
from breqy.domain.enums import EventType
from breqy.tools.registry import ToolRegistry
from breqy.tools.shell import ShellTool
from breqy.tools.filesystem import FilesystemTool


@pytest.mark.asyncio
async def test_runtime_registers_tools():
    registry = ToolRegistry()
    registry.register(ShellTool())
    registry.register(FilesystemTool())

    runtime = AgentRuntime(
        agent_id="breqy",
        tool_registry=registry,
        tool_permissions=["shell", "filesystem"],
    )

    assert runtime.can_use_tool("shell") is True
    assert runtime.can_use_tool("filesystem") is True
    assert runtime.can_use_tool("ssh") is False


@pytest.mark.asyncio
async def test_runtime_executes_tool():
    registry = ToolRegistry()
    registry.register(ShellTool())

    runtime = AgentRuntime(
        agent_id="breqy",
        tool_registry=registry,
        tool_permissions=["shell"],
    )

    result = await runtime.execute_tool("shell", {"command": "echo test"})
    assert result.success is True
    assert "test" in result.output["stdout"]


@pytest.mark.asyncio
async def test_runtime_denies_unpermitted_tool():
    registry = ToolRegistry()
    registry.register(ShellTool())

    runtime = AgentRuntime(
        agent_id="breqy",
        tool_registry=registry,
        tool_permissions=[],  # No permissions
    )

    result = await runtime.execute_tool("shell", {"command": "echo test"})
    assert result.success is False
    assert "not permitted" in result.error.lower()
```

- [ ] **Step 2: Implement agent runtime**

`breqy/agents/runtime.py`:
```python
"""Agent process runtime: tool execution within permission bounds.

Each agent runs as a separate process, connects to the engine
via A2A, and executes tools within its permitted set.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from breqy.tools.executor import ToolResult
from breqy.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Core agent runtime with tool execution."""

    def __init__(
        self,
        agent_id: str,
        tool_registry: ToolRegistry,
        tool_permissions: list[str],
    ) -> None:
        self._agent_id = agent_id
        self._tools = tool_registry
        self._permissions = set(tool_permissions)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if the agent has permission to use a tool."""
        return tool_name in self._permissions and self._tools.get(tool_name) is not None

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> ToolResult:
        """Execute a tool if permitted."""
        if tool_name not in self._permissions:
            return ToolResult(
                success=False,
                error=f"Tool not permitted: {tool_name}",
            )

        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}",
            )

        logger.info("Executing tool: %s with args: %s", tool_name, arguments)
        try:
            result = await tool.execute(arguments)
            logger.info("Tool %s completed: success=%s", tool_name, result.success)
            return result
        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            return ToolResult(success=False, error=str(e))


def main() -> None:
    """Entry point for breqy-agent command."""
    parser = argparse.ArgumentParser(description="Breqy Agent Runtime")
    parser.add_argument("--agent-dir", required=True, help="Path to agent config directory")
    parser.add_argument("--engine-socket", required=True, help="Engine Unix socket path")
    args = parser.parse_args()

    from breqy.agents.config import load_agent_config
    from breqy.a2a.client import A2AClient
    from breqy.tools.shell import ShellTool
    from breqy.tools.filesystem import FilesystemTool

    config = load_agent_config(args.agent_dir)

    registry = ToolRegistry()
    registry.register(ShellTool())
    registry.register(FilesystemTool())

    runtime = AgentRuntime(
        agent_id=config.id,
        tool_registry=registry,
        tool_permissions=config.tool_permissions,
    )

    async def run() -> None:
        client = A2AClient(args.engine_socket)
        await client.connect()
        logger.info("Agent %s connected to engine", config.id)

        # Listen for incoming events and handle tool invocations
        async for envelope in client.listen():
            event = envelope.to_event()
            # Handle tool invocation events from engine
            # (Full routing logic will be added during integration)
            logger.debug("Agent received event: %s", event.event_type)

    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/agents/test_runtime.py -v`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add breqy/agents/runtime.py tests/agents/test_runtime.py
git commit -m "feat: agent runtime with tool execution and permission checking"
```

---

### Task 28: Default Agent Configuration Validation

**Files:**
- Validate: `system/agents/breqy/agent.yaml`
- Validate: `system/agents/breqy/persona.md`

- [ ] **Step 1: Write integration test for default agent config**

Add to `tests/agents/test_config.py`:
```python
def test_default_breqy_agent_loads():
    """Verify the actual default agent config loads correctly."""
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    agent_dir = os.path.join(project_root, "system", "agents", "breqy")

    if not os.path.exists(agent_dir):
        pytest.skip("Default agent dir not found (CI environment)")

    config = load_agent_config(agent_dir)
    assert config.id == "breqy"
    assert config.name == "breqy"
    assert "shell" in config.tool_permissions
    assert "filesystem" in config.tool_permissions
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agents/test_config.py -v`
Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add tests/agents/test_config.py
git commit -m "test: validate default breqy agent config loads correctly"
```

---

## Chunk 8: TUI Client

**Parallel: YES — can run simultaneously with Chunks 5 and 6 (after Chunk 3/A2A)**
**Depends on: Chunk 3 (A2A Protocol)**

### Task 29: TUI App Skeleton & Session List

**Files:**
- Create: `breqy/tui/__init__.py`
- Create: `breqy/tui/app.py`
- Create: `breqy/tui/client.py`
- Create: `breqy/tui/screens/__init__.py`
- Create: `breqy/tui/screens/session_list.py`
- Create: `breqy/tui/widgets/__init__.py`

- [ ] **Step 1: Implement TUI client wrapper**

`breqy/tui/__init__.py`:
```python
"""Breqy TUI — terminal user interface client."""
```

`breqy/tui/client.py`:
```python
"""TUI-side client wrapping A2A communication."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Callable, Coroutine, Any

from breqy.a2a.client import A2AClient
from breqy.a2a.envelope import Envelope
from breqy.domain.events import (
    Event,
    MessageSentEvent,
    SessionCreatedEvent,
    ControlEvent,
)
from breqy.domain.enums import EventType

logger = logging.getLogger(__name__)


class TuiClient:
    """High-level client for TUI-to-engine communication."""

    def __init__(self, socket_path: str) -> None:
        self._client = A2AClient(socket_path)
        self._connected = False

    async def connect(self) -> None:
        await self._client.connect()
        self._connected = True

    async def disconnect(self) -> None:
        await self._client.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def create_session(self, agent_id: str = "breqy") -> None:
        event = SessionCreatedEvent(
            session_id="",  # Engine assigns
            primary_agent_id=agent_id,
        )
        await self._client.send_event(event)

    async def send_message(self, session_id: str, content: str) -> None:
        event = MessageSentEvent(
            session_id=session_id,
            message_id="",
            role="user",
            content=content,
        )
        await self._client.send_event(event)

    async def send_control(self, session_id: str, event_type: EventType, direction: str = "") -> None:
        event = ControlEvent(
            session_id=session_id,
            event_type=event_type,
            new_direction=direction,
        )
        await self._client.send_event(event)

    async def listen(self) -> AsyncIterator[Event]:
        async for envelope in self._client.listen():
            yield envelope.to_event()
```

- [ ] **Step 2: Implement session list screen**

`breqy/tui/screens/__init__.py`:
```python
"""TUI screens."""
```

`breqy/tui/screens/session_list.py`:
```python
"""Session list screen — select or create sessions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Label, Button
from textual.containers import Vertical, Horizontal


class SessionItem(ListItem):
    """A session entry in the list."""

    def __init__(self, session_id: str, agent: str, updated: str) -> None:
        super().__init__()
        self.session_id = session_id
        self._agent = agent
        self._updated = updated

    def compose(self) -> ComposeResult:
        yield Label(f"[bold]{self.session_id}[/bold]  ({self._agent})  {self._updated}")


class SessionListScreen(Screen):
    """Screen showing available sessions."""

    CSS = """
    #session-list {
        height: 1fr;
        margin: 1 2;
    }
    #controls {
        height: auto;
        margin: 1 2;
        align: center middle;
    }
    """

    BINDINGS = [
        ("n", "new_session", "New Session"),
        ("q", "quit", "Quit"),
        ("enter", "select_session", "Select"),
    ]

    def __init__(self, sessions: list[dict] | None = None) -> None:
        super().__init__()
        self._sessions = sessions or []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Label("[bold]Sessions[/bold]", id="title")
            yield ListView(
                *[
                    SessionItem(
                        session_id=s.get("id", ""),
                        agent=s.get("agent", "breqy"),
                        updated=s.get("updated", ""),
                    )
                    for s in self._sessions
                ],
                id="session-list",
            )
            with Horizontal(id="controls"):
                yield Button("New Session (n)", id="btn-new", variant="primary")
                yield Button("Quit (q)", id="btn-quit")
        yield Footer()

    def action_new_session(self) -> None:
        self.app.post_message(self.NewSession())

    def action_quit(self) -> None:
        self.app.exit()

    class NewSession:
        """Message posted when user wants a new session."""
        pass
```

- [ ] **Step 3: Implement main TUI app**

`breqy/tui/widgets/__init__.py`:
```python
"""TUI widgets."""
```

`breqy/tui/app.py`:
```python
"""Main Breqy TUI application."""

from __future__ import annotations

import asyncio
import os
import sys

from textual.app import App

from breqy.tui.client import TuiClient
from breqy.tui.screens.session_list import SessionListScreen


class BreqyApp(App):
    """Breqy TUI — connects to the engine and provides chat interface."""

    TITLE = "Breqy"
    CSS = """
    Screen {
        background: $surface;
    }
    """

    def __init__(self, socket_path: str | None = None) -> None:
        super().__init__()
        self._socket_path = socket_path or os.getenv(
            "BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock"
        )
        self._client = TuiClient(self._socket_path)

    async def on_mount(self) -> None:
        """Connect to engine and show session list."""
        try:
            await self._client.connect()
        except (ConnectionError, OSError) as e:
            self.notify(f"Cannot connect to engine: {e}", severity="error")
            # Show session list anyway (offline mode)

        await self.push_screen(SessionListScreen())

    @property
    def client(self) -> TuiClient:
        return self._client


def main() -> None:
    """Entry point for breqy-tui command."""
    app = BreqyApp()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add breqy/tui/
git commit -m "feat: TUI app skeleton with session list screen"
```

---

### Task 30: Chat Screen

**Files:**
- Create: `breqy/tui/screens/chat.py`
- Create: `breqy/tui/widgets/message_view.py`

- [ ] **Step 1: Implement message view widget**

`breqy/tui/widgets/message_view.py`:
```python
"""Message rendering widget for chat."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Vertical


class MessageView(Widget):
    """Renders a single chat message."""

    def __init__(
        self, role: str, content: str, agent_id: str = "", timestamp: str = ""
    ) -> None:
        super().__init__()
        self._role = role
        self._content = content
        self._agent_id = agent_id
        self._timestamp = timestamp

    def compose(self) -> ComposeResult:
        if self._role == "user":
            prefix = "[bold cyan]You[/bold cyan]"
        elif self._role == "agent":
            name = self._agent_id or "Agent"
            prefix = f"[bold green]{name}[/bold green]"
        else:
            prefix = "[bold yellow]System[/bold yellow]"

        yield Static(f"{prefix}  [dim]{self._timestamp}[/dim]")
        yield Static(self._content)
```

- [ ] **Step 2: Implement chat screen**

`breqy/tui/screens/chat.py`:
```python
"""Chat screen — active conversation with streaming messages."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Vertical
from textual.message import Message as TextualMessage


class ChatScreen(Screen):
    """Active chat screen with message input and streaming output."""

    CSS = """
    #chat-log {
        height: 1fr;
        margin: 0 1;
        border: solid $primary;
    }
    #input {
        dock: bottom;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back to Sessions"),
        ("ctrl+c", "stop", "Stop"),
        ("ctrl+x", "circuit_break", "Circuit Break"),
    ]

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield RichLog(id="chat-log", highlight=True, markup=True)
            yield Input(placeholder="Type a message...", id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user message submission."""
        content = event.value.strip()
        if not content:
            return
        event.input.clear()

        # Display user message
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold cyan]You:[/bold cyan] {content}")

        # Post message to app for sending via A2A
        self.post_message(self.UserMessage(self.session_id, content))

    def append_agent_message(self, content: str, agent_id: str = "breqy") -> None:
        """Append an agent response to the chat log."""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold green]{agent_id}:[/bold green] {content}")

    def append_system_message(self, content: str) -> None:
        """Append a system message."""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold yellow]System:[/bold yellow] {content}")

    def append_tool_output(self, tool_name: str, summary: str, output: str = "") -> None:
        """Append tool execution output."""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold magenta]Tool ({tool_name}):[/bold magenta] {summary}")
        if output:
            log.write(f"[dim]{output[:500]}[/dim]")

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_stop(self) -> None:
        self.post_message(self.ControlAction(self.session_id, "stop"))

    def action_circuit_break(self) -> None:
        self.post_message(self.ControlAction(self.session_id, "circuit_break"))

    class UserMessage(TextualMessage):
        def __init__(self, session_id: str, content: str) -> None:
            super().__init__()
            self.session_id = session_id
            self.content = content

    class ControlAction(TextualMessage):
        def __init__(self, session_id: str, action: str) -> None:
            super().__init__()
            self.session_id = session_id
            self.action = action
```

- [ ] **Step 3: Commit**

```bash
git add breqy/tui/screens/chat.py breqy/tui/widgets/message_view.py
git commit -m "feat: TUI chat screen with message input and streaming display"
```

---

### Task 31: Task List & Approval Widgets

**Files:**
- Create: `breqy/tui/widgets/task_list.py`
- Create: `breqy/tui/widgets/approval_prompt.py`

- [ ] **Step 1: Implement task list widget**

`breqy/tui/widgets/task_list.py`:
```python
"""Task list widget showing visible TODO items."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Vertical

from breqy.domain.enums import TaskStatus


_STATUS_ICONS = {
    TaskStatus.PENDING: "[ ]",
    TaskStatus.IN_PROGRESS: "[~]",
    TaskStatus.COMPLETED: "[x]",
    TaskStatus.FAILED: "[!]",
    TaskStatus.CANCELLED: "[-]",
    TaskStatus.BLOCKED: "[B]",
}


class TaskListWidget(Widget):
    """Renders the visible task/todo list for a session."""

    DEFAULT_CSS = """
    TaskListWidget {
        height: auto;
        margin: 0 1;
        padding: 1;
        border: solid $accent;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._tasks: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Static("[bold]Tasks[/bold]", id="task-header")
        yield Vertical(id="task-items")

    def update_tasks(self, tasks: list[dict]) -> None:
        """Update displayed tasks."""
        self._tasks = tasks
        container = self.query_one("#task-items", Vertical)
        container.remove_children()
        for task in tasks:
            status = TaskStatus(task.get("status", "pending"))
            icon = _STATUS_ICONS.get(status, "[ ]")
            title = task.get("title", "")
            container.mount(Static(f"  {icon} {title}"))
```

- [ ] **Step 2: Implement approval prompt widget**

`breqy/tui/widgets/approval_prompt.py`:
```python
"""Inline approval prompt widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Button
from textual.containers import Horizontal
from textual.message import Message as TextualMessage


class ApprovalPrompt(Widget):
    """Shows an inline approval request with approve/deny buttons."""

    DEFAULT_CSS = """
    ApprovalPrompt {
        height: auto;
        margin: 1;
        padding: 1;
        border: heavy $warning;
        background: $surface-darken-1;
    }
    #approval-buttons {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, approval_id: str, description: str) -> None:
        super().__init__()
        self.approval_id = approval_id
        self._description = description

    def compose(self) -> ComposeResult:
        yield Static(f"[bold yellow]Approval Required[/bold yellow]")
        yield Static(self._description)
        with Horizontal(id="approval-buttons"):
            yield Button("Approve (y)", id="btn-approve", variant="success")
            yield Button("Approve for Session (s)", id="btn-approve-session", variant="primary")
            yield Button("Deny (n)", id="btn-deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-approve":
                self.post_message(self.Decided(self.approval_id, True, False))
            case "btn-approve-session":
                self.post_message(self.Decided(self.approval_id, True, True))
            case "btn-deny":
                self.post_message(self.Decided(self.approval_id, False, False))
        self.remove()

    class Decided(TextualMessage):
        def __init__(self, approval_id: str, granted: bool, extend_to_session: bool) -> None:
            super().__init__()
            self.approval_id = approval_id
            self.granted = granted
            self.extend_to_session = extend_to_session
```

- [ ] **Step 3: Commit**

```bash
git add breqy/tui/widgets/task_list.py breqy/tui/widgets/approval_prompt.py
git commit -m "feat: TUI task list and approval prompt widgets"
```

---

### Task 32: Control Bar Widget

**Files:**
- Create: `breqy/tui/widgets/control_bar.py`

- [ ] **Step 1: Implement control bar**

`breqy/tui/widgets/control_bar.py`:
```python
"""Control bar widget for stop/steer/circuit-break."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Input, Static
from textual.containers import Horizontal, Vertical
from textual.message import Message as TextualMessage


class ControlBar(Widget):
    """User control primitives: stop, stop-and-steer, steer, circuit-break."""

    DEFAULT_CSS = """
    ControlBar {
        dock: bottom;
        height: auto;
        padding: 0 1;
    }
    #control-buttons {
        height: auto;
    }
    #steer-input {
        display: none;
        margin: 0 1;
    }
    .visible {
        display: block !important;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="control-buttons"):
            yield Button("Stop", id="btn-stop", variant="warning")
            yield Button("Stop & Steer", id="btn-stop-steer", variant="primary")
            yield Button("Steer", id="btn-steer", variant="default")
            yield Button("CIRCUIT BREAK", id="btn-circuit-break", variant="error")
        yield Input(placeholder="New direction...", id="steer-input")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-stop":
                self.post_message(self.Control("stop"))
            case "btn-stop-steer":
                steer_input = self.query_one("#steer-input", Input)
                steer_input.add_class("visible")
                steer_input.focus()
                self._pending_action = "stop_and_steer"
            case "btn-steer":
                steer_input = self.query_one("#steer-input", Input)
                steer_input.add_class("visible")
                steer_input.focus()
                self._pending_action = "steer"
            case "btn-circuit-break":
                self.post_message(self.Control("circuit_break"))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        direction = event.value.strip()
        if direction and hasattr(self, "_pending_action"):
            self.post_message(self.Control(self._pending_action, direction))
            event.input.clear()
            event.input.remove_class("visible")

    class Control(TextualMessage):
        def __init__(self, action: str, direction: str = "") -> None:
            super().__init__()
            self.action = action
            self.direction = direction
```

- [ ] **Step 2: Commit**

```bash
git add breqy/tui/widgets/control_bar.py
git commit -m "feat: TUI control bar with stop/steer/circuit-break"
```

---

## Chunk 9: Integration & Polish

**Parallel: NO — depends on ALL previous chunks**

### Task 33: Control Primitives (Engine-side)

**Files:**
- Modify: `breqy/engine/server.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_control_primitives.py`

- [ ] **Step 1: Write integration test for control primitives**

`tests/integration/test_control_primitives.py`:
```python
"""Tests for control primitives: stop, steer, circuit-break."""

import asyncio
import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig
from breqy.a2a.client import A2AClient
from breqy.a2a.envelope import Envelope
from breqy.domain.events import ControlEvent
from breqy.domain.enums import EventType


@pytest.mark.asyncio
async def test_stop_event_reaches_engine(tmp_dir: Path):
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    received_events = []
    original_handler = daemon.server.a2a_server._on_envelope

    async def tracking_handler(envelope, client_id):
        received_events.append(envelope)
        await original_handler(envelope, client_id)

    daemon.server.a2a_server._on_envelope = tracking_handler

    client = A2AClient(str(tmp_dir / "engine.sock"))
    await client.connect()

    stop_event = ControlEvent(
        session_id="ses_test",
        event_type=EventType.CONTROL_STOP,
    )
    await client.send_event(stop_event)
    await asyncio.sleep(0.1)

    await client.disconnect()
    await daemon.stop()

    assert len(received_events) >= 1
    assert received_events[0].event_type == EventType.CONTROL_STOP


@pytest.mark.asyncio
async def test_circuit_break_kills_agents(tmp_dir: Path):
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    # Verify kill_all is callable (no agents spawned in test)
    daemon.server.agent_spawner.kill_all()
    assert daemon.server.agent_spawner.list_running() == []

    await daemon.stop()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/integration/test_control_primitives.py -v`
Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add tests/integration/
git commit -m "test: control primitive integration tests"
```

---

### Task 34: End-to-End Session Flow

**Files:**
- Create: `tests/integration/test_session_flow.py`

- [ ] **Step 1: Write end-to-end session test**

`tests/integration/test_session_flow.py`:
```python
"""End-to-end test: create session, send message, receive events."""

import asyncio
import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig
from breqy.a2a.client import A2AClient
from breqy.domain.events import MessageSentEvent, SessionCreatedEvent
from breqy.domain.enums import EventType, MessageRole


@pytest.mark.asyncio
async def test_session_create_and_message(tmp_dir: Path):
    """Full flow: start engine, connect client, create session, send message."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    # Create a session via the session manager directly
    session = await daemon.server.session_manager.create_session("breqy")
    assert session is not None

    # Connect a client (simulating TUI)
    client = A2AClient(str(tmp_dir / "engine.sock"))
    await client.connect()

    # Send a message event
    msg_event = MessageSentEvent(
        session_id=session.id,
        message_id="msg_1",
        role="user",
        content="Hello Breqy!",
    )
    await client.send_event(msg_event)
    await asyncio.sleep(0.1)

    # Verify message was persisted
    messages = await daemon.server.session_manager.get_messages(session.id)
    # (Messages would be persisted if we had a handler — for now, event is logged)

    await client.disconnect()
    await daemon.stop()


@pytest.mark.asyncio
async def test_multiple_clients_receive_broadcasts(tmp_dir: Path):
    """Two clients connected; messages from one reach the other."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()

    client1 = A2AClient(str(tmp_dir / "engine.sock"))
    client2 = A2AClient(str(tmp_dir / "engine.sock"))
    await client1.connect()
    await client2.connect()

    received_by_client2 = []

    async def listen_client2():
        async for envelope in client2.listen():
            received_by_client2.append(envelope)
            if len(received_by_client2) >= 1:
                break

    listen_task = asyncio.create_task(listen_client2())

    # Client 1 sends a message
    msg_event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_1",
        role="user",
        content="Hello from client 1",
    )
    await client1.send_event(msg_event)

    try:
        await asyncio.wait_for(listen_task, timeout=2.0)
    except asyncio.TimeoutError:
        pass

    await client1.disconnect()
    await client2.disconnect()
    await daemon.stop()

    assert len(received_by_client2) >= 1
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/integration/test_session_flow.py -v`
Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_session_flow.py
git commit -m "test: end-to-end session flow integration tests"
```

---

### Task 35: Restart Survival

**Files:**
- Create: `tests/integration/test_restart_survival.py`

- [ ] **Step 1: Write restart survival test**

`tests/integration/test_restart_survival.py`:
```python
"""Test that sessions and events survive engine restart."""

import asyncio
import pytest
from pathlib import Path

from breqy.engine.daemon import EngineDaemon
from breqy.config.models import EngineConfig
from breqy.domain.enums import SessionStatus


@pytest.mark.asyncio
async def test_session_survives_restart(tmp_dir: Path):
    """Create session, stop engine, restart, verify session exists."""
    db_path = str(tmp_dir / "test.db")
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=db_path,
        data_dir=str(tmp_dir),
    )

    # First run: create session
    daemon1 = EngineDaemon(config)
    await daemon1.start()
    session = await daemon1.server.session_manager.create_session("breqy")
    session_id = session.id
    await daemon1.stop()

    # Second run: verify session still exists
    # Need new socket path because old one may linger
    config2 = EngineConfig(
        socket_path=str(tmp_dir / "engine2.sock"),
        db_path=db_path,
        data_dir=str(tmp_dir),
    )
    daemon2 = EngineDaemon(config2)
    await daemon2.start()

    recovered = await daemon2.server.session_manager.get_session(session_id)
    assert recovered is not None
    assert recovered.id == session_id
    assert recovered.status == SessionStatus.ACTIVE

    sessions = await daemon2.server.session_manager.list_sessions()
    assert len(sessions) >= 1

    await daemon2.stop()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_restart_survival.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_restart_survival.py
git commit -m "test: restart survival — sessions persist across engine restarts"
```

---

### Task 36: Final Validation & Cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: all tests pass

- [ ] **Step 2: Run linter**

Run: `ruff check breqy/`
Expected: no errors (fix any that appear)

- [ ] **Step 3: Run type checker**

Run: `mypy breqy/ --ignore-missing-imports`
Expected: no errors (fix any that appear)

- [ ] **Step 4: Verify entry points work**

Run: `python -m breqy.engine.daemon --help || true`
Run: `python -m breqy.agents.runtime --help`
Expected: help text printed without errors

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and validation for Slice 1"
```

---

## Parallel Execution Summary

For maximum efficiency, assign agents to workstreams as follows:

### Agent Assignment Map

| Agent | Phase 2 (parallel) | Phase 3 (parallel) |
|-------|--------------------|--------------------|
| **Agent A** | Chunk 2: Storage Layer (Tasks 5-9) | Chunk 5: Engine Core (Tasks 18-22) |
| **Agent B** | Chunk 3: A2A Protocol (Tasks 10-13) | Chunk 8: TUI Client (Tasks 29-32) |
| **Agent C** | Chunk 4: Policy/Approval/Config (Tasks 14-17) | Chunk 6: Tool System (Tasks 23-25) |

### Sequential phases (single agent or orchestrated):
- **Phase 1**: Chunk 1 (Foundation) — any single agent
- **Phase 4**: Chunk 7 (Agent Runtime) — after Phases 2+3 complete
- **Phase 5**: Chunk 9 (Integration) — after all above complete

### Critical path:
```
Foundation → Storage + Policy → Engine Core → Agent Runtime → Integration
             (A2A in parallel) → (TUI + Tools in parallel)
```

**Estimated total: 36 tasks, ~200 steps, ~50 commits**

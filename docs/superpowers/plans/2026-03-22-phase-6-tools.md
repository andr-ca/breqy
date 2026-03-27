# Phase 6 Tool System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 6 tool system with native shell/filesystem tools, centralized policy-aware tool orchestration, durable tool invocation persistence, and full MCP discovery/invocation support.

**Architecture:** Native and MCP-backed tools share one `ToolExecutor` contract and one `ToolRegistry`. A new `ToolService` owns policy checks, approval waits, invocation persistence, and runtime event emission so individual tools stay focused on execution only. MCP support is implemented as a real client plus adapter layer, while memory semantics remain out of scope until Phase 7.

**Tech Stack:** Python 3.12, Pydantic v2, asyncio subprocess APIs, aiosqlite, structlog, pytest, pytest-asyncio

---

## File Map

### Create

- `breqy/tools/__init__.py` - public exports for tool contracts, registry, and concrete tools
- `breqy/tools/executor.py` - `ToolExecutor`, `ToolResult`, and optional metadata model if needed
- `breqy/tools/registry.py` - registration and lookup for native and MCP-backed tools
- `breqy/tools/service.py` - central orchestration for policy, approval, persistence, and events
- `breqy/tools/shell.py` - native shell tool
- `breqy/tools/filesystem.py` - native filesystem tool
- `breqy/tools/mcp.py` - MCP server config, client, bootstrap, and adapter classes
- `breqy/storage/sqlite/tool_invocation_repo.py` - SQLite persistence for `ToolInvocation`
- `tests/unit/tools/__init__.py`
- `tests/unit/tools/test_executor.py`
- `tests/unit/tools/test_service.py`
- `tests/unit/tools/test_shell.py`
- `tests/unit/tools/test_filesystem.py`
- `tests/unit/tools/test_mcp.py`
- `tests/unit/storage/test_tool_invocation_repo.py`

### Modify

- `breqy/storage/interfaces.py` - add `ToolInvocationRepository` interface
- `breqy/storage/sqlite/__init__.py` - export tool invocation repository if exports are used
- `breqy/config/models.py` - add MCP server config models or engine-level MCP config fields
- `breqy/config/loader.py` - support loading MCP config from YAML
- `breqy/engine/server.py` - compose `ToolService` if Phase 6 wires engine-level execution now
- `breqy/domain/events.py` - only if current tool event schemas need additional fields for correct tool lifecycle reporting
- `breqy/domain/enums.py` - only if an explicit waiting-for-approval status is required and agreed during implementation
- `docs/architecture.md` - describe tool execution flow and MCP integration
- `CHANGES.md` - record Phase 6 changes
- `.env.sample` - add sanitized MCP-related examples if environment variables are introduced

### Existing References to Read During Implementation

- `docs/superpowers/specs/2026-03-22-phase-6-tools-design.md`
- `breqy/policy/evaluator.py`
- `breqy/policy/filesystem.py`
- `breqy/policy/approval.py`
- `breqy/domain/models.py`
- `breqy/domain/events.py`
- `breqy/storage/sqlite/migrations.py`

---

### Task 1: Tool Contract and Registry

**Files:**
- Create: `breqy/tools/__init__.py`
- Create: `breqy/tools/executor.py`
- Create: `breqy/tools/registry.py`
- Create: `tests/unit/tools/__init__.py`
- Test: `tests/unit/tools/test_executor.py`

- [ ] **Step 1: Write the failing tests for tool contracts and registry**

`tests/unit/tools/test_executor.py`

```python
import pytest

from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.registry import ToolRegistry


class EchoTool(ToolExecutor):
    name = "echo"
    description = "Echo text"

    async def execute(self, arguments: dict[str, object]) -> ToolResult:
        text = str(arguments.get("text", ""))
        return ToolResult(
            success=True,
            output={"echoed": text},
            summary=f"Echoed: {text}",
        )


def test_tool_registry_register_and_get() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.get("missing") is None
    assert "echo" in registry.list_tools()


@pytest.mark.asyncio
async def test_tool_result_round_trip() -> None:
    result = await EchoTool().execute({"text": "hello"})

    assert result.success is True
    assert result.output == {"echoed": "hello"}
    assert result.error == ""


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())
```

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run: `uv run pytest tests/unit/tools/test_executor.py -v`
Expected: FAIL with import errors because `breqy.tools.executor` and `breqy.tools.registry` do not exist yet.

- [ ] **Step 3: Implement the minimal tool contract layer**

Create `breqy/tools/executor.py` with:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    summary: str = ""


class ToolExecutor(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError
```

Create `breqy/tools/registry.py` with:

```python
from __future__ import annotations

from breqy.tools.executor import ToolExecutor


class ToolRegistry:
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

Create `breqy/tools/__init__.py` exporting the public API.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_executor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit the tool contract layer**

```bash
git add breqy/tools/__init__.py breqy/tools/executor.py breqy/tools/registry.py tests/unit/tools/__init__.py tests/unit/tools/test_executor.py
git commit -m "feat(tools): add tool contract and registry"
```

---

### Task 2: Tool Invocation Repository

**Files:**
- Modify: `breqy/storage/interfaces.py`
- Create: `breqy/storage/sqlite/tool_invocation_repo.py`
- Modify: `breqy/storage/sqlite/__init__.py`
- Test: `tests/unit/storage/test_tool_invocation_repo.py`

- [ ] **Step 1: Write failing tests for tool invocation persistence**

`tests/unit/storage/test_tool_invocation_repo.py`

```python
import pytest

from breqy.domain.enums import ToolStatus
from breqy.domain.models import ToolInvocation, Session
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.tool_invocation_repo import SqliteToolInvocationRepository


@pytest.mark.asyncio
async def test_create_and_get_tool_invocation(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(
        session_id=session.id,
        agent_id="breqy",
        tool_name="shell",
        arguments={"command": "echo hello"},
    )

    await repo.create(invocation)
    loaded = await repo.get(invocation.id)

    assert loaded is not None
    assert loaded.tool_name == "shell"
    assert loaded.arguments["command"] == "echo hello"


@pytest.mark.asyncio
async def test_update_status_and_result(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    invocation = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    await repo.create(invocation)

    await repo.update_result(
        invocation.id,
        status=ToolStatus.COMPLETED,
        result={"stdout": "ok", "return_code": 0},
        error="",
        summary="Command exited with code 0",
    )

    loaded = await repo.get(invocation.id)
    assert loaded is not None
    assert loaded.status == ToolStatus.COMPLETED
    assert loaded.result == {"stdout": "ok", "return_code": 0}
    assert loaded.summary == "Command exited with code 0"


@pytest.mark.asyncio
async def test_list_by_session_returns_newest_first(db_connection):
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="breqy")
    await session_repo.create(session)

    repo = SqliteToolInvocationRepository(db_connection)
    first = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="shell")
    second = ToolInvocation(session_id=session.id, agent_id="breqy", tool_name="filesystem")
    await repo.create(first)
    await repo.create(second)

    invocations = await repo.list_by_session(session.id)

    assert [item.id for item in invocations] == [second.id, first.id]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/storage/test_tool_invocation_repo.py -v`
Expected: FAIL because `SqliteToolInvocationRepository` and the storage interface do not exist yet.

- [ ] **Step 3: Add the abstract interface and SQLite implementation**

Modify `breqy/storage/interfaces.py` to add:

```python
class ToolInvocationRepository(ABC):
    @abstractmethod
    async def create(self, invocation: ToolInvocation) -> None: ...

    @abstractmethod
    async def get(self, invocation_id: str) -> ToolInvocation | None: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[ToolInvocation]: ...

    @abstractmethod
    async def update_result(
        self,
        invocation_id: str,
        status: ToolStatus,
        result: dict[str, Any] | None,
        error: str,
        summary: str,
        approval_id: str | None = None,
    ) -> None: ...
```

Create `breqy/storage/sqlite/tool_invocation_repo.py` following the existing repository patterns in `session_repo.py`, `message_repo.py`, and `approval_repo.py`.

Implementation requirements:
- JSON-serialize `arguments` and `result`
- map `status` using `ToolStatus`
- store `completed_at` when the invocation is finalized
- return rows as `ToolInvocation` domain models
- order `list_by_session()` by `started_at DESC`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/storage/test_tool_invocation_repo.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit the repository work**

```bash
git add breqy/storage/interfaces.py breqy/storage/sqlite/tool_invocation_repo.py breqy/storage/sqlite/__init__.py tests/unit/storage/test_tool_invocation_repo.py
git commit -m "feat(storage): add tool invocation repository"
```

---

### Task 3: Native Shell Tool

**Files:**
- Create: `breqy/tools/shell.py`
- Test: `tests/unit/tools/test_shell.py`

- [ ] **Step 1: Write the failing tests for shell execution**

`tests/unit/tools/test_shell.py`

```python
import pytest

from breqy.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_echo() -> None:
    result = await ShellTool(timeout=5).execute({"command": "echo hello"})

    assert result.success is True
    assert "hello" in result.output["stdout"]
    assert result.output["return_code"] == 0


@pytest.mark.asyncio
async def test_shell_non_zero_exit() -> None:
    result = await ShellTool(timeout=5).execute({"command": "false"})

    assert result.success is False
    assert result.output["return_code"] != 0


@pytest.mark.asyncio
async def test_shell_timeout() -> None:
    result = await ShellTool(timeout=1).execute({"command": "sleep 5"})

    assert result.success is False
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_requires_command() -> None:
    result = await ShellTool().execute({})

    assert result.success is False
    assert "command" in result.error.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_shell.py -v`
Expected: FAIL because `ShellTool` does not exist yet.

- [ ] **Step 3: Implement the minimal shell tool**

Create `breqy/tools/shell.py` using `asyncio.create_subprocess_shell`.

Implementation requirements:
- use `structlog`
- accept constructor default timeout
- support `command` and optional `cwd`
- support optional `timeout_seconds` override from arguments
- return `ToolResult` with `stdout`, `stderr`, and `return_code`
- kill and await the subprocess on timeout before returning failure

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_shell.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit the shell tool**

```bash
git add breqy/tools/shell.py tests/unit/tools/test_shell.py
git commit -m "feat(tools): add shell tool"
```

---

### Task 4: Native Filesystem Tool

**Files:**
- Create: `breqy/tools/filesystem.py`
- Test: `tests/unit/tools/test_filesystem.py`

- [ ] **Step 1: Write the failing tests for filesystem operations**

`tests/unit/tools/test_filesystem.py`

```python
from pathlib import Path

import pytest

from breqy.tools.filesystem import FilesystemTool


@pytest.mark.asyncio
async def test_read_file(tmp_dir: Path) -> None:
    path = tmp_dir / "input.txt"
    path.write_text("hello", encoding="utf-8")

    result = await FilesystemTool().execute({"operation": "read", "path": str(path)})

    assert result.success is True
    assert result.output["content"] == "hello"


@pytest.mark.asyncio
async def test_write_file(tmp_dir: Path) -> None:
    path = tmp_dir / "out.txt"

    result = await FilesystemTool().execute(
        {"operation": "write", "path": str(path), "content": "new content"}
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new content"


@pytest.mark.asyncio
async def test_edit_file(tmp_dir: Path) -> None:
    path = tmp_dir / "edit.txt"
    path.write_text("old text here", encoding="utf-8")

    result = await FilesystemTool().execute(
        {
            "operation": "edit",
            "path": str(path),
            "old_string": "old text",
            "new_string": "new text",
        }
    )

    assert result.success is True
    assert path.read_text(encoding="utf-8") == "new text here"


@pytest.mark.asyncio
async def test_delete_file(tmp_dir: Path) -> None:
    path = tmp_dir / "delete.txt"
    path.write_text("delete me", encoding="utf-8")

    result = await FilesystemTool().execute({"operation": "delete", "path": str(path)})

    assert result.success is True
    assert not path.exists()


@pytest.mark.asyncio
async def test_invalid_operation() -> None:
    result = await FilesystemTool().execute({"operation": "invalid", "path": "/tmp/x"})

    assert result.success is False


@pytest.mark.asyncio
async def test_edit_fails_when_old_text_missing(tmp_dir: Path) -> None:
    path = tmp_dir / "edit.txt"
    path.write_text("original", encoding="utf-8")

    result = await FilesystemTool().execute(
        {
            "operation": "edit",
            "path": str(path),
            "old_string": "missing",
            "new_string": "replacement",
        }
    )

    assert result.success is False
    assert "not found" in result.error.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_filesystem.py -v`
Expected: FAIL because `FilesystemTool` does not exist yet.

- [ ] **Step 3: Implement the minimal filesystem tool**

Create `breqy/tools/filesystem.py`.

Implementation requirements:
- use `structlog`
- handle `read`, `write`, `edit`, `delete`
- use UTF-8 for text IO
- create parent directories for `write`
- replace only the first matching occurrence for `edit`
- return structured `ToolResult`
- add a helper such as `derive_operations(arguments) -> list[FilesystemOperation]` to support orchestration-time policy checks

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_filesystem.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit the filesystem tool**

```bash
git add breqy/tools/filesystem.py tests/unit/tools/test_filesystem.py
git commit -m "feat(tools): add filesystem tool"
```

---

### Task 5: Tool Service Orchestration

**Files:**
- Create: `breqy/tools/service.py`
- Modify: `breqy/domain/events.py` (only if required for correct tool lifecycle reporting)
- Test: `tests/unit/tools/test_service.py`

- [ ] **Step 1: Write failing tests for orchestration behavior**

`tests/unit/tools/test_service.py`

Use test doubles for the dependencies (`ToolRegistry`, `ApprovalService`, invocation repo, event bus) and exercise only orchestration behavior.

Minimum tests:

```python
@pytest.mark.asyncio
async def test_service_executes_allowed_tool(...):
    ...


@pytest.mark.asyncio
async def test_service_rejects_denied_tool(...):
    ...


@pytest.mark.asyncio
async def test_service_fails_for_unknown_tool(...):
    ...


@pytest.mark.asyncio
async def test_service_requests_approval_before_execution(...):
    ...


@pytest.mark.asyncio
async def test_service_stops_when_approval_denied(...):
    ...


@pytest.mark.asyncio
async def test_service_blocks_filesystem_operation_when_path_denied(...):
    ...


@pytest.mark.asyncio
async def test_service_records_failure_when_tool_raises(...):
    ...
```

Assertions must cover:
- unknown tool fails without calling any executor
- invocation persistence starts before execution
- `ApprovalRequestedEvent` is published before any tool execution begins
- started and completed/failed events are published only after execution is actually allowed to begin
- approval request path creates and waits on approval
- policy denial prevents tool execution
- filesystem path denial prevents filesystem execution
- approval denial prevents tool execution

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_service.py -v`
Expected: FAIL because `ToolService` does not exist yet.

- [ ] **Step 3: Implement the minimal orchestration service**

Create `breqy/tools/service.py`.

Implementation requirements:
- use constructor injection only
- resolve tools from `ToolRegistry`
- evaluate tool-level policy with resource `tool:<tool_name>`
- if the tool is `filesystem`, derive filesystem operations and run filesystem policy checks before execution
- fail fast for unknown tools before attempting execution
- create and persist a `ToolInvocation`
- if approval is required, create request and await `ApprovalService.wait_for_decision()`
- publish `ApprovalRequestedEvent` immediately after creating the approval request
- persist the invocation in a pre-execution waiting state before awaiting approval
- publish `ToolInvocationStartedEvent` only after policy/approval gates have passed and execution is actually about to start
- on denial, timeout, or filesystem path denial, finalize invocation without calling the tool
- on success, persist completion and publish `ToolInvocationCompletedEvent`
- on exception, persist failure and publish `ToolInvocationFailedEvent`

Status note:
- because `ToolStatus` has no dedicated waiting-for-approval value today, store the invocation in `PENDING` before approval resolves, then move it to `RUNNING` only when execution actually begins

Do not wire this into the engine yet if that would block clean unit tests; keep the service independently testable first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit the orchestration service**

```bash
git add breqy/tools/service.py breqy/domain/events.py tests/unit/tools/test_service.py
git commit -m "feat(tools): add policy-aware tool service"
```

---

### Task 6: MCP Config, Client, and Adapter

**Files:**
- Create: `breqy/tools/mcp.py`
- Modify: `breqy/config/models.py`
- Modify: `breqy/config/loader.py`
- Test: `tests/unit/tools/test_mcp.py`

- [ ] **Step 1: Write failing tests for MCP config and adapter behavior**

`tests/unit/tools/test_mcp.py`

Minimum tests:

```python
def test_mcp_server_config_model_accepts_process_transport():
    ...


@pytest.mark.asyncio
async def test_mcp_tool_adapter_delegates_execution_to_client():
    ...


@pytest.mark.asyncio
async def test_bootstrap_registers_namespaced_tools_from_multiple_servers():
    ...


@pytest.mark.asyncio
async def test_bootstrap_skips_failed_server_and_keeps_working_tools():
    ...


@pytest.mark.asyncio
async def test_discovery_failure_is_logged_and_does_not_crash_bootstrap():
    ...


@pytest.mark.asyncio
async def test_invocation_transport_failure_returns_predictable_tool_failure():
    ...


@pytest.mark.asyncio
async def test_malformed_remote_result_is_normalized_to_failure():
    ...
```

Use fakes for transport/protocol; do not depend on a real external MCP server in unit tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_mcp.py -v`
Expected: FAIL because the MCP module and config models do not exist yet.

- [ ] **Step 3: Implement MCP config and adapter layer**

Implementation requirements:
- add typed MCP server configuration to `breqy/config/models.py`
- update `breqy/config/loader.py` to accept MCP config from YAML
- create `MCPServerConfig`, `MCPClient`, `MCPToolAdapter`, and a bootstrap helper in `breqy/tools/mcp.py`
- normalize discovered tools into namespaced local tool names such as `mcp.<server_id>.<tool_name>`
- ensure one failed server does not stop bootstrap of the rest
- treat startup failure, discovery failure, invocation transport failure, and malformed remote result payloads as graceful failures
- use `structlog` for structured failure context

Important constraint:
- keep the transport/protocol boundary isolated enough that later real MCP transport details can evolve without forcing changes to `ToolService`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tools/test_mcp.py -v`
Expected: PASS

- [ ] **Step 5: Commit the MCP layer**

```bash
git add breqy/tools/mcp.py breqy/config/models.py breqy/config/loader.py tests/unit/tools/test_mcp.py
git commit -m "feat(tools): add MCP client and adapter layer"
```

---

### Task 7: Integration Wiring, Docs, and Changelog

**Files:**
- Modify: `breqy/tools/__init__.py`
- Modify: `breqy/engine/server.py`
- Modify: `docs/architecture.md`
- Modify: `CHANGES.md`
- Modify: `.env.sample` (if MCP env vars are added)

- [ ] **Step 1: Write or extend a failing integration-style test for wiring**

Choose the smallest integration point that proves the service path is usable from the engine layer.

Recommended target:
- add a test that creates `ToolService` with real `ToolRegistry`, `SqliteToolInvocationRepository`, `EventBus`, and `EventWriter`, then verifies an allowed shell or filesystem execution persists invocation state and emits tool events that are also written through the event-writer path.

If engine wiring is added directly in `breqy/engine/server.py`, add a focused test for the composed dependency.

- [ ] **Step 2: Run the selected test to verify it fails**

Run: `uv run pytest <exact-test-target> -v`
Expected: FAIL because the final wiring is not complete yet.

- [ ] **Step 3: Wire the completed tool system into the engine-facing surface**

Implementation requirements:
- export the public tool API in `breqy/tools/__init__.py`
- compose `ToolService` where the engine/runtime will actually use it
- avoid introducing concrete storage imports into business logic that should stay abstracted

- [ ] **Step 4: Update documentation**

Update `docs/architecture.md` with:
- native tool execution flow
- policy/approval gate location
- MCP bootstrap and remote tool registration flow

Update `CHANGES.md` with Phase 6 additions.

If MCP configuration uses environment variables, update `.env.sample` with sanitized examples.

- [ ] **Step 5: Run the full focused Phase 6 test suite**

Run:

```bash
uv run pytest tests/unit/tools/ tests/unit/storage/test_tool_invocation_repo.py -v
```

Expected: PASS

- [ ] **Step 6: Run the full project test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS with no regressions.

- [ ] **Step 7: Commit the final wiring and documentation**

```bash
git add breqy/tools/__init__.py breqy/engine/server.py docs/architecture.md CHANGES.md .env.sample
git commit -m "feat(tools): wire tool system into engine and document Phase 6"
```

---

## Verification Checklist

- [ ] Native tool contract and registry are in place
- [ ] `ToolInvocationRepository` exists and persists the existing `tool_invocations` table
- [ ] `ShellTool` passes all contract tests
- [ ] `FilesystemTool` passes all contract tests
- [ ] `ToolService` enforces tool policy and approval flow
- [ ] Filesystem operations are checked before mutation
- [ ] MCP bootstrap registers remote tools without crashing on partial failure
- [ ] Tool lifecycle events are emitted and persisted through the bus/event writer path
- [ ] Architecture docs and changelog are updated
- [ ] Full test suite passes

---

## Notes for Implementers

- Follow TDD strictly: RED -> GREEN -> REFACTOR for every task.
- Use `structlog.get_logger(__name__)` in new engine/tool/policy-facing modules.
- Keep tool classes free of policy, approval, and storage concerns.
- Do not add memory-domain logic in this phase.
- If event schema changes become necessary, make them explicit and update tests first.
- If `.env.sample` is touched, keep values sanitized.

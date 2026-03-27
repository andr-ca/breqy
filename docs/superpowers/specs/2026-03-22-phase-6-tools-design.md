# Design: Phase 6 Tool System

**Date:** 2026-03-22
**Scope:** Slice 1
**Status:** Approved pending spec review

---

## Overview

Phase 6 adds the execution layer that lets agents and the engine run approved tools through one consistent contract. The system must support two native tools in Slice 1 (`shell` and `filesystem`) and a full MCP integration path that can discover and invoke remote tools through the same registry and orchestration flow.

This spec intentionally expands the older Slice 1 wording in `agents/project.instructions.md`, which limited MCP to extension points. In this session, the user explicitly approved full MCP transport, discovery, and invocation as part of Phase 6. Planning and implementation for this phase should treat that as the authoritative scope override for this workstream.

This phase introduces a clear separation of concerns:
- tool implementations perform tool-specific work
- a central tool orchestration service applies policy, approval, persistence, and event emission
- a registry resolves native and MCP-backed tools through one lookup surface
- the MCP client manages transport, discovery, and remote invocation

Phase 6 does **not** implement memory-domain semantics. It provides the MCP substrate that Phase 7 will use for memory-backed tools.

---

## Goals

By the end of Phase 6, the following must be true:

1. `ToolExecutor` and `ToolResult` define the canonical contract for tool execution.
2. `ToolRegistry` can register and resolve both native tools and MCP-backed tools.
3. A central tool orchestration service evaluates tool policy before execution.
4. Filesystem operations are checked against filesystem policy before execution.
5. Approval-required tool calls create durable approval requests and resume after a decision.
6. Tool invocations are persisted and published as typed runtime events.
7. `ShellTool` executes subprocess commands with timeout, return code, and structured output capture.
8. `FilesystemTool` supports read, write, edit, and delete with structured operation metadata.
9. MCP servers can be configured, started or connected to, queried for tool manifests, and invoked through the same tool service contract.
10. MCP transport or discovery failure degrades gracefully without crashing the engine.

---

## Explicit Non-Goals

- No memory-domain behavior yet (session/global/private memory remains Phase 7).
- No SSH tool yet.
- No Docker or delegation tools yet.
- No direct agent writes to storage.
- No bypass path that allows tools to skip policy or approval checks.

---

## Invocation API

Phase 6 uses explicit argument contracts so native tools and MCP-backed tools can be invoked consistently.

### ShellTool arguments

Required:
- `command: str`

Optional:
- `timeout_seconds: int`
- `cwd: str`

Not included in v1:
- per-invocation environment overrides
- argv-list mode alongside shell-string mode

Rules:
- `command` is always a shell command string
- if `timeout_seconds` is absent, the tool default is used
- if `cwd` is absent, execution uses the current process working directory

Result shape:
- `output["stdout"]: str`
- `output["stderr"]: str`
- `output["return_code"]: int`

### FilesystemTool arguments

Common required fields:
- `operation: str`
- `path: str`

Operation-specific fields:

`read`
- no additional fields

`write`
- `content: str`

`edit`
- `old_string: str`
- `new_string: str`

`delete`
- no additional fields

Rules:
- text operations use UTF-8
- `edit` replaces the first matching occurrence only
- directory-recursive operations are out of scope in Phase 6

Result shape examples:
- `read` -> `output["content"]: str`
- `write` -> summary-only success is acceptable
- `edit` -> summary-only success is acceptable
- `delete` -> summary-only success is acceptable

### MCP-backed tool arguments

MCP-backed tools accept the remote tool's declared argument shape unchanged. The local adapter passes the argument dict through and normalizes the returned data into `ToolResult`.

---

## Approval Lifecycle

Approval-required execution is synchronous from the caller's perspective in Phase 6.

Execution model:
- `ToolService.execute_tool(...)` creates an approval request when policy requires approval
- the service persists the `ToolInvocation` in a waiting state and publishes `ApprovalRequestedEvent`
- the service then awaits `ApprovalService.wait_for_decision(...)` in memory
- if approval is granted, execution continues in the same call path
- if approval is denied or expires, execution stops and the invocation is finalized as denied/failed

Restart behavior:
- in-flight approval waits do **not** automatically resume after engine restart in Phase 6
- approval requests and decisions remain durable in storage for visibility and audit
- after restart, the caller must reissue the tool request if execution should be attempted again

This is an intentional Phase 6 simplification. Automatic resumption of pending tool invocations after restart is out of scope for this phase.

---

## Architecture

### 1. Tool Contract Layer

**Files:**
- `breqy/tools/__init__.py`
- `breqy/tools/executor.py`

This layer defines the common interface for all tools.

#### `ToolResult`

`ToolResult` remains the normalized return type for all tool executions.

Required fields:
- `success: bool`
- `output: dict[str, Any]`
- `error: str`
- `summary: str`

Rules:
- `output` contains structured result data, not presentation-only strings
- `summary` is concise and human-readable for event and UI surfaces
- failures should prefer structured `error` text over raising raw exceptions to callers when the failure is an expected execution outcome

#### `ToolExecutor`

All tools implement:

```python
class ToolExecutor(ABC):
    name: str
    description: str

    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...
```

This contract applies to:
- native tools such as `ShellTool`
- native tools such as `FilesystemTool`
- MCP-backed adapter tools created from discovered remote manifests

#### Optional metadata companion

The implementation may add a separate metadata model such as `ToolSpec` or `RegisteredTool` if needed for:
- source (`native` vs `mcp`)
- schema or argument hints
- owning MCP server ID

This metadata must not replace the core `ToolExecutor` execution contract.

---

### 2. Tool Registry

**File:** `breqy/tools/registry.py`

`ToolRegistry` owns registration and resolution of all executable tools.

Responsibilities:
- register native tool instances
- register MCP-backed adapter tool instances
- reject duplicate names
- list registered tools with stable names
- resolve a tool by name

Required behavior:
- duplicate registration raises `ValueError`
- unknown tool lookup returns `None`
- registration order must not affect lookup correctness

Naming rules:
- native tools use simple names like `shell` and `filesystem`
- MCP tools use explicit namespaced identifiers to avoid collisions

Recommended MCP naming convention:
- `mcp.<server_id>.<tool_name>`

Example:
- `mcp.memory-server.search_records`

The exact delimiter may vary, but the convention must be:
- deterministic
- collision-safe
- reversible enough to recover the backing server/tool identity

---

### 3. Tool Orchestration Service

**File:** `breqy/tools/service.py`

This is the most important addition in Phase 6. It is the single entry point used by the engine or runtime when executing a tool.

#### Purpose

Tool implementations should not own policy, approval, eventing, or persistence. Those concerns belong in one orchestration service.

#### Responsibilities

`ToolService` (or `ToolRunner` if the final name fits better) is responsible for:
- resolving a tool from `ToolRegistry`
- evaluating tool policy through `PolicyEvaluator`
- applying filesystem policy for filesystem operations before execution
- creating approval requests through `ApprovalService` when policy requires approval
- persisting `ToolInvocation` state through the appropriate repository
- publishing `ToolInvocationStartedEvent`, `ToolOutputChunkEvent` when supported, and `ToolInvocationCompletedEvent` or `ToolInvocationFailedEvent`
- normalizing failures into `ToolResult` or domain exceptions

#### Dependencies

Constructor-injected dependencies should include:
- `ToolRegistry`
- `PolicyEvaluator`
- filesystem policy checker
- `ApprovalService`
- repository or service to persist `ToolInvocation`
- `EventBus`
- `EventWriter` pathway already connected through the bus

If a dedicated `ToolInvocationRepository` does not exist yet, this phase may either:
- add it cleanly behind storage interfaces, or
- use an engine-owned persistence adapter that encapsulates storage details

The final design must still keep business logic out of concrete storage code.

#### Execution flow

1. Receive request: `session_id`, `agent_id`, `tool_name`, `arguments`
2. Resolve tool from registry
3. If not found, return failed result or raise `ToolExecutionError`
4. Evaluate tool access policy against resource `tool:<tool_name>`
5. If denied, raise `PolicyDeniedError`
6. If tool is filesystem-related, derive requested filesystem operations and evaluate them with filesystem policy
7. If approval is required:
   - create `ApprovalRequest`
   - publish `ApprovalRequestedEvent`
   - mark the invocation as waiting for approval
   - wait in-memory for decision through `ApprovalService.wait_for_decision(...)`
   - if denied or expired, stop execution
8. Persist `ToolInvocation` as started/running
9. Publish `ToolInvocationStartedEvent`
10. Execute tool
11. Persist completion or failure
12. Publish completion/failure event
13. Return normalized `ToolResult`

#### Error handling

The service must distinguish between:
- policy denial
- approval denial
- approval timeout
- tool execution failure
- unknown tool
- transport/discovery failure for MCP-backed tools

Expected failures should be surfaced predictably, using domain errors where policy/runtime semantics matter.

Approval-required execution must follow the approval lifecycle defined above; the phase does not include automatic restart-time resumption of waiting invocations.

---

### 4. Shell Tool

**File:** `breqy/tools/shell.py`

`ShellTool` is a focused subprocess runner.

Responsibilities:
- validate command presence
- execute subprocess through asyncio APIs
- enforce timeout
- capture stdout/stderr
- report return code
- return structured `ToolResult`

Rules:
- no policy logic inside the tool
- no approval logic inside the tool
- no persistence or event publishing inside the tool
- timeout must terminate the subprocess and return a failure result

Output shape:
- `stdout`
- `stderr`
- `return_code`

Stretch behavior that is allowed in this phase if implementation stays small:
- incremental output callback support for future event streaming

That support must remain optional and must not complicate the basic execute contract.

---

### 5. Filesystem Tool

**File:** `breqy/tools/filesystem.py`

`FilesystemTool` supports:
- `read`
- `write`
- `edit`
- `delete`

Responsibilities:
- validate required arguments
- perform file operations
- return structured results
- expose enough operation metadata for orchestration-time policy checks

#### Policy integration design

The filesystem tool itself should not evaluate policy. Instead, it must make operation intent easy to inspect.

Recommended internal helper contract:
- derive a list of requested operations before doing work
- map each request to `FilesystemOperation`

Examples:
- `read` -> `FilesystemOperation.READ`
- `write` -> `FilesystemOperation.WRITE`
- `edit` -> `FilesystemOperation.WRITE`
- `delete` -> `FilesystemOperation.DELETE`

This can be exposed by either:
- a helper method on `FilesystemTool`, or
- a separate request-normalization utility used by `ToolService`

The chosen shape must keep policy evaluation outside direct file mutation code.

#### Operation behavior

`read`:
- returns file contents
- returns failure for missing file

`write`:
- creates parent directories as needed
- writes provided content

`edit`:
- reads file
- replaces first matching occurrence
- returns failure if target text is missing

`delete`:
- removes a file
- returns failure if file does not exist

This phase covers file operations only. Directory tree editing, globbing, and recursive deletes are out of scope unless already required by the tests.

---

### 6. MCP Integration

**File:** `breqy/tools/mcp.py`

Phase 6 includes full MCP client support for remote tool discovery and invocation.

#### Scope of MCP support

Included:
- MCP server configuration model
- client lifecycle
- transport startup or connection management
- tool discovery
- invocation of remote tools
- adaptation into local `ToolExecutor` contract
- graceful degradation on failure

Excluded from this phase:
- memory-domain semantics
- promotion workflows
- special-case MCP memory business logic

#### Components

##### `MCPServerConfig`

A typed model describing one MCP server.

Expected fields:
- `id`
- `transport` (for Slice 1, process-backed transport is the required baseline)
- `command`
- `args`
- optional `env`
- optional startup timeout
- optional request timeout

If Phase 6 needs additional fields, they must stay focused on MCP transport/config and not drift into memory semantics.

##### `MCPClient`

Responsibilities:
- start the configured MCP server process or establish the required transport
- perform MCP handshake/initialization
- list available tools
- invoke a tool with arguments
- stop or clean up transport resources

The client must hide protocol details from the rest of the system.

##### `MCPToolAdapter`

Wrap one discovered MCP tool and expose it as a local `ToolExecutor`.

Responsibilities:
- hold the server identity and remote tool name
- delegate execute calls through `MCPClient`
- normalize remote responses into `ToolResult`

#### Startup behavior

The system should support a bootstrap step such as:
- load configured MCP servers
- initialize each server independently
- discover tools
- register each discovered tool into `ToolRegistry`

Failure model:
- one broken MCP server must not stop native tools from working
- one broken MCP server must not prevent other MCP servers from loading
- failures should be logged with structured context

#### Invocation behavior

For an MCP-backed tool:
- policy still runs on the registered local tool name
- approval still runs in the central orchestration service
- invocation persistence and events are identical to native tools
- only the execution backend differs

This keeps the engine and TUI blind to whether a tool is native or remote.

---

## Persistence and Events

### Tool Invocation Persistence

Every tool execution request should produce a durable `ToolInvocation` record.

Lifecycle:
- create pending/approved or running invocation record before execution
- attach approval request ID if approval is required
- write result or error and completion timestamp on exit

If Phase 6 reveals that the storage interface layer is missing a dedicated abstraction for tool invocations, that gap should be filled in this phase in a way consistent with the existing repository pattern.

### Tool Events

Phase 6 should use existing typed events:
- `ToolInvocationStartedEvent`
- `ToolInvocationCompletedEvent`
- `ToolInvocationFailedEvent`
- `ToolOutputChunkEvent` when supported
- `ApprovalRequestedEvent`
- `ApprovalDecidedEvent` from the approval path

Rules:
- all events are published on the in-process `EventBus`
- persistence still happens via the existing `EventWriter` subscriber path
- the TUI and agent runtime should not need custom ad hoc payloads to understand tool state

If additional event fields are needed for correct tool UX, they should be added by evolving the typed schemas, not by sending raw dict extras through the system.

---

## Interfaces and Dependency Boundaries

To keep Phase 6 modular and testable:

- `ToolExecutor` is the only execution interface tools must satisfy
- `ToolRegistry` handles resolution, not policy
- `ToolService` handles orchestration, not direct file/process details
- `ShellTool` and `FilesystemTool` do not know about policy or storage
- `MCPClient` knows transport/protocol, not policy or session approval
- storage remains behind interfaces and constructor injection

No tool should import concrete SQLite code directly.

---

## Testing Strategy

### Unit tests

#### `tests/unit/tools/test_executor.py`
- registry registers and resolves tools
- duplicate registration is rejected
- simple tool execution returns normalized `ToolResult`

#### `tests/unit/tools/test_service.py`
- allows permitted tool execution
- denies policy-blocked tool execution
- requests approval for approval-gated tool execution
- aborts on approval denial
- aborts on approval timeout
- records invocation lifecycle correctly
- publishes expected events

#### `tests/unit/tools/test_shell.py`
- successful command
- non-zero exit command
- timeout path
- missing command input

#### `tests/unit/tools/test_filesystem.py`
- read file
- write file
- edit file
- delete file
- invalid operation
- missing path
- edit target not found

#### `tests/unit/tools/test_mcp.py`
- client initializes configured server
- discovery returns tool manifests
- discovered tools are registered with namespaced names
- adapter invokes remote tool and normalizes response
- one server failing to initialize does not break others
- remote invocation failure becomes predictable tool failure

### Integration expectations

At least one integration-style path in this phase should verify:
- tool execution through orchestration
- event emission through the bus
- durable invocation state written correctly

This phase should not rely only on isolated unit tests around individual tool classes.

---

## Failure Modes

The implementation plan must explicitly cover these failure modes:

- unknown tool requested
- duplicate tool registration
- policy denied tool call
- filesystem policy denied path access
- approval denied tool call
- approval timeout
- shell command timeout
- shell subprocess execution error
- filesystem target missing
- MCP server startup failure
- MCP discovery failure
- MCP invocation transport failure
- MCP server returning malformed or incomplete result data

Each must have one clear owner:
- orchestration service for policy/approval/lifecycle failures
- tool implementations for direct execution failures
- MCP client for transport/protocol failures

---

## Phase Breakdown Guidance

This design is still one phase, but planning should likely split implementation into smaller tasks such as:

1. tool contract + registry
2. orchestration service + persistence/events wiring
3. shell tool
4. filesystem tool
5. MCP config + client + adapter + registry bootstrap
6. integration verification and documentation

The implementation plan should preserve TDD within each task.

---

## Documentation Impact

Phase 6 implementation should update:
- architecture notes for tool execution flow
- any quickstart/setup docs needed for MCP server configuration
- `CHANGES.md`

If MCP configuration introduces environment variables, `.env.sample` must be updated with sanitized examples.

---

## Open Decisions Resolved Here

- Phase 6 includes a full MCP client path, not a stub.
- MCP support covers discovery and invocation, not memory semantics.
- Tool execution policy and approval stay centralized in orchestration, not in tool classes.
- Native and MCP-backed tools must share one registry and one execution path.

---

## Ready for Planning

This spec is ready to be converted into an implementation plan once it passes spec review and user review.

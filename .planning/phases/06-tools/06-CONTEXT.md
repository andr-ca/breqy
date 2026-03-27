# Phase 6: Tools - Context

**Gathered:** 2026-03-22
**Status:** Complete and verified

<domain>
## Phase Boundary

Phase 6 delivers the engine-facing tool execution layer: native shell/filesystem tools, a centralized policy- and approval-aware tool service, durable tool invocation persistence, and full MCP client/bootstrap support so remote tools can be invoked through the same registry and execution path.

</domain>

<decisions>
## Implementation Decisions

### Tool Invocation Contract
- Native tools use stable names `shell` and `filesystem`; MCP-backed tools use `mcp.<server_id>.<tool_name>` to avoid collisions.
- `ShellTool` accepts a single `command: str` plus optional `cwd` and `timeout_seconds`.
- `FilesystemTool` uses one tool interface with `operation`, `path`, and operation-specific fields (`content`, `old_string`, `new_string`).
- Approval-required tool execution waits synchronously inside `ToolService` after persistence and `ApprovalRequestedEvent` emission.

### Policy and Execution Lifecycle
- Policy and approval logic live only in `ToolService`, not in individual tool classes.
- `ToolInvocationStartedEvent` fires only after policy and approval gates pass and execution is actually starting.
- Pre-execution invocation state remains `ToolStatus.PENDING` until execution begins; no new waiting status is introduced in Phase 6.
- Filesystem policy is derived from requested `FilesystemOperation` values and checked before any file mutation occurs.

### MCP Integration
- Process-backed MCP servers are the Phase 6 transport baseline.
- One failed MCP server degrades gracefully; other MCP servers and native tools continue working.
- Malformed remote tool results are normalized at the adapter boundary into failed `ToolResult` values.
- Phase 6 builds enough real MCP support that a memory tool can register through the system, but memory semantics remain Phase 7 scope.

### Docs, Artifacts, and Phase Boundary
- The existing Phase 6 spec and plan are reused as the authoritative planning basis rather than regenerating different versions.
- New execution artifacts live under `.planning/phases/06-tools/`.
- `STATE.md` and `ROADMAP.md` should mark Phase 6 in progress during execution and complete only after verification passes and summary artifacts exist.
- Phase 6 completed on 2026-03-23 with fresh focused verification and a full green project suite.
- The GSD worktree patch is workflow infrastructure, not a Breqy product deliverable.

### the agent's Discretion
- The exact delimiter is flexible if `mcp.<server_id>.<tool_name>` proves awkward in implementation, as long as MCP tool names remain deterministic, namespaced, and collision-safe.
- Event schema changes should only be made if implementation proves the existing typed tool events are insufficient.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `breqy/tools/executor.py` and `breqy/tools/registry.py` already establish the initial tool contract and registry.
- `breqy/storage/sqlite/tool_invocation_repo.py` provides invocation persistence against the existing `tool_invocations` table.
- `breqy/policy/evaluator.py`, `breqy/policy/filesystem.py`, and `breqy/policy/approval.py` provide the core gating primitives Phase 6 needs.
- `breqy/engine/event_bus.py` and `breqy/engine/event_writer.py` provide the event path for tool lifecycle streaming and persistence.

### Established Patterns
- Storage uses constructor-injected repository interfaces with dedicated SQLite implementations.
- Engine and policy modules use `structlog.get_logger(__name__)` rather than stdlib logging.
- Async behavior is implemented with narrow focused classes and unit tests under `tests/unit/`.
- Phase execution so far has used TDD with small commits per task plus review-driven fix commits.

### Integration Points
- `ToolService` will sit between agent/runtime callers and concrete tool executors.
- Filesystem gating integrates with `FilesystemPolicyChecker` before mutation.
- Approval flow integrates with `ApprovalService` and existing approval events.
- Tool lifecycle events integrate with `EventBus` and persist via the existing event-writer subscriber path.
- Engine composition likely lands in `breqy/engine/server.py` once the tool system is ready to wire in.

</code_context>

<specifics>
## Specific Ideas

- Reuse the existing Phase 6 spec at `docs/superpowers/specs/2026-03-22-phase-6-tools-design.md` and implementation plan at `docs/superpowers/plans/2026-03-22-phase-6-tools.md` as the planning baseline.
- Treat Phase 6 as the full MCP client/discovery/invocation phase, even though older project docs called MCP beyond extension points out of scope; that earlier wording is overridden for this workstream.

</specifics>

<deferred>
## Deferred Ideas

- Session/global/agent-private memory semantics and promotion behavior stay in Phase 7.
- Any richer MCP transport support beyond the process-backed baseline is deferred.

</deferred>

# Phase 6 Plan 03: Orchestration and MCP

Status: ready for execution
Source: `docs/superpowers/plans/2026-03-22-phase-6-tools.md`
Source tasks: 5-6

Goal:
Add the policy-aware orchestration layer and full MCP bootstrap, discovery, and adapter support.

Scope:
- `breqy/tools/service.py`
- `breqy/tools/mcp.py`
- `breqy/config/models.py`
- `breqy/config/loader.py`
- `breqy/domain/events.py` only if schema changes are required
- `tests/unit/tools/test_service.py`
- `tests/unit/tools/test_mcp.py`

Requirements covered:
- TOOL-03
- TOOL-04
- TOOL-05
- TOOL-06 substrate

Execution notes:
- `ToolService` is the single entry point for policy, approval, persistence, and lifecycle events.
- Unknown-tool and policy-denied paths must fail before executor invocation.
- Approval-required executions stay in `PENDING` until execution actually begins.
- MCP server failures must degrade gracefully without blocking native tools or other MCP servers.

Verification targets:
- `uv run pytest tests/unit/tools/test_service.py -v`
- `uv run pytest tests/unit/tools/test_mcp.py -v`

Done when:
- Tool execution is policy-aware and approval-aware.
- Filesystem operations are derived and checked before mutation.
- MCP servers register namespaced tools like `mcp.<server_id>.<tool_name>`.
- Discovery and invocation failures normalize to predictable tool failures.

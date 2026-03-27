# Phase 6 Plan 01: Tool Foundation and Persistence

Status: ready for execution
Source: `docs/superpowers/plans/2026-03-22-phase-6-tools.md`
Source tasks: 1-2

Goal:
Build the core tool contract, tool registry, and durable tool invocation persistence layer.

Scope:
- `breqy/tools/__init__.py`
- `breqy/tools/executor.py`
- `breqy/tools/registry.py`
- `breqy/storage/interfaces.py`
- `breqy/storage/sqlite/tool_invocation_repo.py`
- `breqy/storage/sqlite/__init__.py`
- `tests/unit/tools/test_executor.py`
- `tests/unit/storage/test_tool_invocation_repo.py`

Requirements covered:
- TOOL-01
- TOOL-02

Execution notes:
- Follow TDD exactly.
- Reuse the existing `tool_invocations` table and current repository patterns.
- Keep business logic on interfaces, not concrete SQLite imports.

Verification targets:
- `uv run pytest tests/unit/tools/test_executor.py -v`
- `uv run pytest tests/unit/storage/test_tool_invocation_repo.py -v`

Done when:
- `ToolExecutor` and `ToolResult` are the canonical tool contract.
- `ToolRegistry` registers, resolves, lists, and rejects duplicate tool names.
- `ToolInvocationRepository` persists and reloads invocation lifecycle records.

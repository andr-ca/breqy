# Phase 6 Plan 04: Engine Wiring and Docs

Status: ready for execution
Source: `docs/superpowers/plans/2026-03-22-phase-6-tools.md`
Source task: 7

Goal:
Wire the completed tool system into the engine-facing surface and finish Phase 6 documentation and verification.

Scope:
- `breqy/tools/__init__.py`
- `breqy/engine/server.py`
- `docs/architecture.md`
- `CHANGES.md`
- `.env.sample` if MCP-related environment examples are introduced
- focused integration-style test target chosen during execution

Requirements covered:
- TOOL-03
- TOOL-04
- TOOL-05
- TOOL-06 substrate

Execution notes:
- Keep engine composition abstracted; do not leak concrete storage details into business logic.
- Update docs only after implementation behavior is verified.
- `.env.sample` must stay sanitized.

Verification targets:
- `uv run pytest tests/unit/tools/ tests/unit/storage/test_tool_invocation_repo.py -v`
- `uv run pytest -q`

Done when:
- Engine-facing composition can execute the tool service path.
- Tool lifecycle events flow through the existing event bus and writer path.
- Architecture and changelog reflect Phase 6 behavior.
- Focused Phase 6 tests and the full suite pass.

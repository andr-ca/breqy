# Phase 6 Plan 02: Native Tools

Status: ready for execution
Source: `docs/superpowers/plans/2026-03-22-phase-6-tools.md`
Source tasks: 3-4

Goal:
Implement the native `shell` and `filesystem` tools on top of the shared contract.

Scope:
- `breqy/tools/shell.py`
- `breqy/tools/filesystem.py`
- `tests/unit/tools/test_shell.py`
- `tests/unit/tools/test_filesystem.py`

Requirements covered:
- TOOL-03
- TOOL-04

Execution notes:
- Keep policy, approval, and persistence logic out of tool classes.
- Use `structlog.get_logger(__name__)` in new modules.
- `FilesystemTool` must expose operation intent clearly enough for orchestration-time filesystem policy checks.

Verification targets:
- `uv run pytest tests/unit/tools/test_shell.py -v`
- `uv run pytest tests/unit/tools/test_filesystem.py -v`

Done when:
- `ShellTool` handles success, non-zero exits, missing command input, and timeout cleanup.
- `FilesystemTool` supports `read`, `write`, `edit`, and `delete` with structured `ToolResult` output.
- Filesystem edits replace only the first matching occurrence.

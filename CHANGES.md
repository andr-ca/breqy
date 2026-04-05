# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `breqy/tools/browser.py` and `breqy/tools/browser_runtime.py`: native Playwright-backed `browser` tool with typed action validation for navigate/click/fill/select/wait/extract/screenshot/history/tab/session/header/cookie operations, plus safe blocked-flow handling for CAPTCHA/MFA/blocked access.
- `tests/unit/tools/test_browser.py` and `tests/unit/tools/test_browser_registry.py`: browser-tool contract coverage for schema validation, blocked/error behavior, transport-safe artifact output, and registry exposure.
- `approval_grants` persistence plus structured approval grant support: once/session/forever scopes, durable `grant_key` matching, and browser-ready action+domain grant semantics across `breqy/domain/`, `breqy/storage/`, and `breqy/policy/approval.py`.
- `ApprovalPrompt` forever approval UX (`F`) and app/engine approval-decision routing so TUI approval choices now produce typed `ApprovalDecidedEvent` messages.
- `AgentLogsScreen` now has a live-filtering search bar (`f` to focus, `c` to clear). Typing a substring instantly shows only matching lines from the ring buffer. A new `filter_lines(lines, filter_str)` pure helper handles case-insensitive filtering. `_lines: deque[str]` (maxlen=1000) buffers all lines since the screen opened; new lines from polls extend the buffer first before any display update.
- `breqy/tui/screens/agent_logs.py`: `AgentLogsScreen` overlay screen that live-tails the agent subprocess log file (e.g. `~/.breqy/data/logs/agent-breqy.log`). Exposes three pure helper utilities: `resolve_agent_log_path()` (respects `BREQY_DATA_DIR`), `read_tail(path, n)` (last 200 lines on open), and `read_new_lines(path, offset)` (incremental 0.5 s poll). Handles missing file (waiting placeholder), `OSError` on poll (silent resume), and agent restart (offset preserved). Close with `q` or `Escape`.
- `/logs` slash command: registered in `ChatScreen._build_command_registry()`, routed in `BreqyApp.on_command_executed` to push `AgentLogsScreen`. App now tracks `_current_agent_id` from `AgentLifecycleEvent` to resolve the correct log file path.
- `tests/unit/tui/test_agent_logs_screen.py`: 9 unit tests for the pure log helpers (path resolution, tail slicing, missing/empty file, incremental poll, file disappear/reappear).
- `tests/unit/tui/test_slash_commands.py`: 2 tests confirming `/logs` is registered and dispatches the `"logs"` token.
- `agents/providers/copilot_client.py`: added `initiator=` field to both LLM provider debug log calls for per-round observability.
- `agents/runtime.py`: extract tool result text from `content` dict (priority: `stdout` → `content` → JSON) instead of the plain `summary` string; append `stderr` when non-empty. Promoted "Provider stream started" to `logger.info` with `initiator=` field.
- `breqy/tui/widgets/selectable_rich_log.py`: `SelectableRichLog` subclass of `RichLog` that enables Textual's built-in text selection and clipboard support. Adds `Strip.apply_offsets` for mouse hit-testing and selection highlight rendering that `RichLog` does not implement. Includes `_apply_selection_highlight` helper for applying styles to character ranges within a `Strip`, and overrides `get_selection` to extract text from actual log content.
- `tests/tui/test_selectable_rich_log.py`: 20 unit tests covering subclass contract, write/clear, selection offsets, selection_updated cache invalidation, get_selection (single-line, multi-line, empty), and `_apply_selection_highlight` edge cases.
- `breqy/tui/clipboard.py`: `copy_to_system_clipboard` helper that tries `xclip`, `xsel`, `wl-copy`, and `pbcopy` as subprocess fallbacks for environments where OSC 52 is unreliable (e.g. tmux without `set-clipboard on`).
- `tests/tui/test_clipboard.py`: 5 tests for clipboard tool fallback chain, error handling, and empty-string no-op.
- Auto-copy on mouse selection: `BreqyApp.on_text_selected` extracts selected text and pushes it to both OSC 52 and system clipboard immediately when the user finishes dragging.
- `breqy/policy/` package: `PolicyDecision` model and `PolicyEvaluator` with most-restrictive-wins rule resolution across global, agent, and session scopes.
- `tests/unit/policy/test_evaluator.py`: 9 unit tests covering all scope combinations, default-allow, DENY/REQUIRE_APPROVAL priority, prefix resource matching, and session isolation. 100% branch and statement coverage.
- `GEMINI.md` instructions for Gemini CLI.
- `.geminiignore` for workspace boundary enforcement.
- `CHANGES.md` (initial mandatory changelog).
- Phase 6 tooling surface: public `breqy.tools` exports for native tools, MCP adapters, registry, and `ToolService`.
- `tests/unit/engine/test_server.py`: integration-style coverage proving engine-composed tool execution persists tool invocation state and writes typed tool lifecycle events through the event-writer path.
- `breqy/memory/` package exports for `MemoryService`, `VectorIndex`, and agent-private memory contracts.
- `breqy/storage/sqlite/memory_repo.py`: SQLite `MemoryRepository` for canonical session/global memory records and promotion state.
- `breqy/tools/memory.py`: local MCP-shaped memory tools for `search`, `write`, and `promote`.
- `tests/integration/memory/test_restart_survival.py`, `tests/integration/memory/test_global_memory.py`, and `tests/integration/memory/test_mediated_access.py` for restart survival, cross-session global reads, and mediated-access verification.
- `agents/breqy/agent.yaml` and `agents/breqy/persona.md` as the canonical default agent definition for the Phase 8 runtime.
- `breqy/agents/` runtime surface: typed runtime models, provider adapters, auth adapters, `CredentialStore`, `SkillLoader`, and agent-owned delegated private-memory helpers.
- `tests/unit/agents/` and `tests/integration/agents/` coverage for credential storage, provider auth/execution adapters, skill loading, runtime streaming/tool dispatch, delegated private-memory flow, and end-to-end engine/runtime round trips.

### Fixed
- `CopilotProvider.stream()` now catches `CopilotAuthError` from `get_copilot_token()` (e.g. HTTP 404 on token exchange when OAuth token is expired/revoked) and triggers device flow re-authentication instead of crashing with an unrecoverable error message. Both the initial token fetch and the 401 retry path are covered.

### Changed
- `agents/core.instructions.md`, `agents/project.instructions.md`, and `agents/python.instructions.md` now include stronger guidance for migration discipline, PR scope hygiene, review-comment handling, approval-contract alignment, best-effort shutdown cleanup, external-surface hardening, and third-party schema compatibility based on lessons from the browser-tool PR review cycle.
- `breqy/tools/service.py` now honors tool-specific approval metadata and skips repeat approval prompts when a matching session/forever grant already exists.
- `breqy/agents/runtime.py` now expands legacy tool permission aliases (`fs`, `memory`) to canonical native/MCP tool names, while adding browser permission support for the default agent manifest.
- `breqy/engine/server.py` default registry now advertises the native `browser` tool and routes typed approval decisions back into `ApprovalService`.
- `docs/architecture.md` now documents the browser tool, structured approval grants, and transport-safe browser artifact handling.
- Replaced `RichLog` with `SelectableRichLog` in all four TUI widgets that display scrollable log content: `ChatView` (chat-log), `TaskPanel` (task-log), `ToolPanel` (tool-log), and `LogsScreen` (logs-display). Enables mouse-drag text selection and clipboard copy across all log panels.
- Refined `GEMINI.md` with full technology stack, correct coverage thresholds, and fixed table formatting.
- Narrowed `.geminiignore` to ensure `.env.sample` is unignored by removing the leading space in the negation pattern.
- Wired engine-side tool composition so `EngineServer` can build a default native tool registry, expose a server-level tool execution entrypoint, and keep tool audit events on the existing centralized event bus and writer path.
- Expanded `docs/architecture.md` with the native tool execution flow, policy and approval gate placement, and the current MCP bootstrap/registration mechanism without implying runtime auto-wiring that does not yet exist.
- Added Phase 7 engine-owned memory contracts, SQLite persistence, retrieval ranking boundary, promotion workflow, and typed memory events across `breqy/domain/`, `breqy/storage/`, and `breqy/memory/`.
- Wired default engine composition so `EngineServer` and `EngineDaemon` build canonical memory services, register local MCP-style memory tools, emit durable memory events, and reject default-runtime private-memory operations until Phase 8 wiring exists.
- Hardened `ToolService` and memory tool adapters so engine-trusted execution context overrides caller-supplied memory scope ownership fields.
- Expanded `docs/architecture.md` to describe the Phase 7 mediated memory path, promotion-only global writes, deterministic filter-then-rank retrieval, and the deferred private-memory runtime boundary.
- Extended `breqy/config/`, `breqy/domain/`, `breqy/engine/`, and `breqy/a2a/` for Phase 8 so the default agent loads from disk, registers with the engine, receives canonical `AgentWorkRequestedEvent` dispatches, streams assistant output, requests engine-mediated tool execution, and persists final assistant turns canonically.
- Restored `EngineConfig.policy_rules` and `EngineConfig.filesystem_policies` after a regression that broke daemon-composed policy and filesystem defaults.
- Completed the Phase 8 private-memory boundary so `private` memory operations stay agent-owned, are delegated only to the owning runtime, and return through typed request/result transport events instead of becoming engine-owned writes.
- Hardened skill loading so skill instruction files must stay inside the skill directory and must be Markdown.
- Isolated provider subprocess authentication so runtime adapters inject credentials from `CredentialStore` while stripping ambient CLI auth state via isolated `HOME`, `XDG_CONFIG_HOME`, and provider config directories.
- Updated `docs/architecture.md` for the Phase 8 runtime dispatch path, transport-only tool/private-memory handoff events, canonical top-level `skills/`, and the API-key decisions for Gemini and Qwen.
- Phase 9 Sessions & Control: restart survival, participant tracking, 4 control primitives (stop, stop-and-steer, steer, circuit-break), canonical task state owned by engine, workspace scoping with path validation at attachment time.
- Phase 10 TUI Client: `breqy/tui/` package with multi-screen Textual application (270 new tests).
  - Foundation: `SessionState` dataclass, `StreamBuffer` for chunk assembly, `EventDispatcher` mapping EventType to handler, `CommandRegistry` for slash commands.
  - App shell: `BreqyApp(App)` with CSS theming, screen navigation, A2A Worker with exponential backoff reconnection.
  - 7 widgets: `MessageInput`, `ChatView` (streaming), `TaskPanel`, `ToolPanel`, `ApprovalPrompt` (FIFO queue), `ControlBar` (stop/steer/circuit-break), `AgentStatusBar`.
  - 5 screens: `SessionListScreen` (DataTable), `ChatScreen` (composes all widgets), `AuthScreen` (device/PKCE/API-key flows), `LogsScreen` (ring buffer, prefix filter), `ModelSelectScreen` (provider/model DataTable).
  - Integration tests covering full startup-to-chat flow, message round-trip, approval flow, control stop, and screen accessibility.

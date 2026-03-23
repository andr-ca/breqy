# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `breqy/policy/` package: `PolicyDecision` model and `PolicyEvaluator` with most-restrictive-wins rule resolution across global, agent, and session scopes.
- `tests/unit/policy/test_evaluator.py`: 9 unit tests covering all scope combinations, default-allow, DENY/REQUIRE_APPROVAL priority, prefix resource matching, and session isolation. 100% branch and statement coverage.
- `GEMINI.md` instructions for Gemini CLI.
- `.geminiignore` for workspace boundary enforcement.
- `CHANGES.md` (initial mandatory changelog).
- Phase 6 tooling surface: public `breqy.tools` exports for native tools, MCP adapters, registry, and `ToolService`.
- `tests/unit/engine/test_server.py`: integration-style coverage proving engine-composed tool execution persists tool invocation state and writes typed tool lifecycle events through the event-writer path.

### Changed
- Refined `GEMINI.md` with full technology stack, correct coverage thresholds, and fixed table formatting.
- Narrowed `.geminiignore` to ensure `.env.sample` is unignored by removing the leading space in the negation pattern.
- Wired engine-side tool composition so `EngineServer` can build a default native tool registry, expose a server-level tool execution entrypoint, and keep tool audit events on the existing centralized event bus and writer path.
- Expanded `docs/architecture.md` with the native tool execution flow, policy and approval gate placement, and the current MCP bootstrap/registration mechanism without implying runtime auto-wiring that does not yet exist.

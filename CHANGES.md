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
- `breqy/tools/shell.py` with `ShellTool`, an async subprocess-based shell runner with configurable `cwd`, per-call timeout override, captured stdout/stderr, and timeout cleanup.
- `tests/unit/tools/test_shell.py` covering successful execution, non-zero exits, timeout handling, and missing command validation.

### Changed
- Refined `GEMINI.md` with full technology stack, correct coverage thresholds, and fixed table formatting.
- Narrowed `.geminiignore` to ensure `.env.sample` is unignored by removing the leading space in the negation pattern.

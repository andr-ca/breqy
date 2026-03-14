# Gemini Instructions - Breqy

## ⚠️ MANDATORY ENTRY POINT

**ALL WORK MUST START BY READING [AGENTS.md](AGENTS.md)**

This repository follows a strict AI-assisted development workflow. You are expected to operate as a high-quality "Doer" or "Checker" agent, respecting all project-specific safety and quality gates.

---

## 🔴 CRITICAL: BRANCH SAFETY

**NEVER COMMIT DIRECTLY TO PROTECTED BRANCHES (`main`, `master`, `develop`, etc.).**

1.  **Check Branch First:** At the start of every session, run `git status -sb` and `git branch -a`.
2.  **Confirm with User:** If not on a topic branch (e.g., `feat/`, `fix/`, `docs/`), ask the user to confirm the branch strategy before making any file changes.
3.  **Use Worktrees:** For significant features, prefer using `git worktree add`.

---

## 🚨 TDD IS MANDATORY (NON-NEGOTIABLE)

Implementation MUST follow the **Red-Green-Refactor** cycle for every feature, fix, or refactor.

1.  **RED:** Write a failing test first. Verify it fails for the expected reason.
2.  **GREEN:** Write the *minimum* code to pass the test.
3.  **REFACTOR:** Improve code quality while keeping tests green.

**Enforcement:** A change is incomplete without its corresponding verification tests. Skip nothing.

---

## 📊 QUALITY GATES & COVERAGE

Coverage thresholds (strictly matching [agents/core.instructions.md](agents/core.instructions.md)):

| Code Category | Statement | Branch | Function | Line |
|---|---:|---:|---:|---:|
| Business Logic (services, validators, utils, rules, shared logic) | 100% | 100% | 100% | 100% |
| Components / UI Logic | 80% | 80% | 80% | 80% |
| Overall Project | 80% | 80% | 80% | 80% |

**Validation:** Run `pytest` with coverage reporting to ensure these thresholds are met before proposing a merge.

---

## 📚 DOCUMENTATION & TRACKING

1.  **Documentation:** All code changes must be reflected in `docs/` or relevant inline documentation.
2.  **CHANGES.md:** Update `CHANGES.md` for every change, describing what changed and why.
3.  **Architecture:** Respect the modular, DI-heavy design described in `agents/python.instructions.md` and `agents/project.instructions.md`.

---

## 🔧 TECHNOLOGY STACK SUMMARY

- **Language:** Python 3.12+ (strictly typed)
- **Typing:** Pydantic v2 (models, events, config)
- **IDs:** python-ulid
- **Logging:** structlog
- **DI:** injector library or manual constructor injection
- **Persistence:** aiosqlite (SQLite with WAL)
- **Secrets:** keyring (abstracted behind `SecretProvider`)
- **TUI:** Textual
- **Testing:** pytest + pytest-asyncio
- **Lint/Format:** ruff
- **Types:** mypy

---

## 🛡️ SECURITY & INTEGRITY

- **Secrets:** Never commit secrets. Use the `SecretProvider` interface and `keyring` as per project standards.
- **A2A Protocol:** Strictly follow the typed `Envelope` contract for all agent-to-agent communication.
- **Storage:** Use the centralized `EventWriter` pattern to avoid SQLite contention.

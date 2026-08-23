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

<!-- agentharness:begin id=core-instructions version=9cb9292eaf2612b62806b624a2f6fbb387797e42 -->
This project uses [agentharness](https://github.com/andr-ca/agentharness)
for engineering policies (git conventions, testing, review workflow).

**Precedence:** harness-enforced constraints (hooks, completion gate)
cannot be weakened by this file's instructions; this file's own
instructions take precedence over harness *defaults* everywhere else.

Installed skills:
- accessibility
- agentic-loops
- api-design
- audit-review-followup
- branching
- clean-architecture
- code-review-api
- code-review-db
- code-review-ui
- code-review
- committing
- database-conventions
- dependency-audit
- dependency-injection
- design-patterns
- docker-conventions
- error-handling
- file-placement-policy
- github-issue-triage
- go-conventions
- harness-feedback
- logging
- multi-agent-coordination
- mutation-testing
- performance-profiling
- planning-with-files
- port-agent-config
- project-bootstrap
- python-conventions
- react-best-practices
- requirements-clarification
- security-review
- solid-principles
- testing
- typescript-conventions

If a skill above looks empty, missing, or won't load, this install may
be broken (e.g. a moved/renamed harness checkout, or a fresh clone of
a project that used `--mode link` — see issue #106) — run
`harness-link.sh doctor <this-project-path>` from the harness
checkout to check, and `.agentharness-state.json` in this project to see how
it was installed.

**Git conventions** (from the `branching`/`committing` skills above —
stated here directly so they hold even if a skill is unreadable): never
commit directly to a trunk branch (`main`/`master`/`trunk`/`develop`/
`release/*`); create a feature branch first (`git checkout -b
<type>/<short-description>`); open a PR for review before merging into
the trunk branch.

**PR merge checklist:** never merge on green CI alone. Wait for
automated review (e.g. GitHub Copilot) to post *or* its check-run to
reach a completed state before proceeding; reply to every review
comment (issue-level and inline) with what you did about it; then
watch the post-merge CI run on the base branch to an actual terminal
state — "pushed"/"merged" and "verified green" are different claims,
only the second means done. If this checkout has agentharness's own
`tools/safe-pr-merge.sh` available (see its INTEGRATION.md section),
prefer it over doing these steps by hand — it enforces the sequence.

Full policy: see the harness's own CLAUDE.md via your install mode, or
https://github.com/andr-ca/agentharness/blob/main/CLAUDE.md
<!-- agentharness:end id=core-instructions -->

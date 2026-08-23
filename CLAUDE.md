# CLAUDE.md — Breqy

Claude Code project instructions. Read this before any tool call, file edit, or code change.

---

## What this project is

Breqy is a **Linux-first, always-on, multi-agent AI assistant** built as a local persistent runtime. Three separate processes communicate over a typed A2A (agent-to-agent) protocol over Unix sockets:

- **breqy-engine** — long-running daemon owning sessions, events, memory, task state, policy
- **breqy agent processes** — separate OS processes with persona, tools, and private memory
- **breqy-tui** — Textual TUI connecting only to the engine

Python 3.12+, Pydantic v2, aiosqlite, Textual, structlog, python-ulid, keyring, pytest, ruff, mypy.

Full context: `agents/project.instructions.md` | PRD: `docs/prd.md` | Architecture: `docs/architecture.md`

---

## Mandatory instructions — read before working

| File | Contains |
|---|---|
| `agents/core.instructions.md` | Branch safety, TDD, git workflow, coverage thresholds, commit rules |
| `agents/project.instructions.md` | Architecture constraints, domain model, Slice 1 scope, tech stack |
| `agents/python.instructions.md` | Python 3.12 modular design, DI, SOLID, import rules |
| `agents/tdd.instructions.md` | Red-Green-Refactor cycle and test quality standards |

---

## Development commands

```bash
# Install dependencies
uv sync                         # or: pip install -e ".[dev]"

# Run tests
pytest                          # all tests
pytest tests/unit/              # unit only
pytest tests/integration/       # integration only
pytest --cov=breqy --cov-report=term-missing  # with coverage

# Lint and format
ruff check .                    # lint
ruff format .                   # format

# Type checking
mypy breqy/

# Run engine (once implemented)
python -m breqy.engine

# Run TUI (once implemented)
python -m breqy.tui
```

---

## Critical constraints — must not violate

**Branch safety**
- Never commit directly to `main`, `master`, `develop`, or `sandbox*`
- Always confirm branch with the user before any file operation
- Branch naming: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`

**TDD — non-negotiable**
- Write failing test first, then implement
- Never write implementation before the test exists and fails
- Coverage thresholds: 100% statement/branch/function/line for business logic; 80% overall

**Architecture — hard rules**
- All storage behind repository interfaces; inject via DI — never import concrete impls in business logic
- Agents do not write to the DB directly — all writes go through the engine's centralized `EventWriter`
- Every approval request, decision, and tool invocation must be written to the event log before or atomically with execution
- `PolicyEvaluator` validates tool access independently — skills never grant permissions
- All secrets via `SecretProvider` interface — never in plain YAML or hardcoded
- A2A messages use canonical typed `Envelope` with shared Pydantic models — no loosely shaped payloads

**Scope**
- Active target is **Slice 1 only** — do not implement Slice 2 features (memory retrieval/promotion, SSH, agent delegation, Docker, artifact tracking) unless explicitly instructed

**Environment variables**
- Never hardcode secrets or env vars
- Always maintain `.env.sample` alongside any `.env` usage

**Documentation**
- Update `docs/` and `CHANGES.md` after implementation
- Undocumented code is incomplete code

---

## Commit format

```
<type>(<scope>): <short description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

---

## Key reference files

| Purpose | File |
|---|---|
| Implementation plan (Slice 1) | `docs/plans/2026-03-13-breqy-slice-1.md` |
| AI delivery lifecycle | `docs/ai_delivery_approach_v_1.md` |
| Architecture decisions | `docs/decisions.md` |
| Lessons learned schema | `docs/lessons_learned_schema.md` |
| Shaped task schema | `docs/shaped_task_schema.md` |

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

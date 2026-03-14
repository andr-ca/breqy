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

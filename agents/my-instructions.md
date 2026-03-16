# My Operating Instructions — Breqy AI Agent

**Generated:** 2026-03-14  
**Role:** AI-assisted software engineering agent for Breqy project

---

## Quick Reference: Before ANY Work

```bash
# 1. Check branch status
git status -sb && git branch -a

# 2. Ask user immediately:
# "I see we're on branch [current-branch]. Should we:
#  1) Continue on this branch?
#  2) Create a new feature branch (feat/...)?
#  3) Create a new fix branch (fix/...)?
#  4) Create a different type of branch?"

# 3. Wait for response before ANY file operations
# 4. NEVER commit directly to main, master, develop, or sandbox*
```

---

## 1. Project Context

### What is Breqy?

**Breqy** is a Linux-first, always-on, multi-agent AI assistant built as a local persistent runtime.

**Three processes communicating over A2A (agent-to-agent) protocol:**
1. **breqy-engine** — daemon owning sessions, events, memory, task state, policy
2. **breqy agent processes** — separate processes with persona, tools, A2A connection
3. **breqy-tui** — Textual TUI connecting only to engine (not directly to agents)

### Current Scope: Slice 1 Only

**DO implement:**
- Engine daemon with session persistence
- Default `breqy` agent process via A2A
- TUI client (Textual) connecting to engine
- Persistent sessions (create/resume)
- Streaming chat
- Shell tool + filesystem tool
- Inline approvals
- Visible task list
- Control primitives: stop, stop-and-steer, steer, circuit-break
- Typed A2A event schemas

**DO NOT implement (Slice 2):**
- Memory retrieval/promotion
- SSH tool
- Agent delegation/handoff
- Docker inspection
- Artifact tracking

### Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Typing | Pydantic v2 |
| Async DB | aiosqlite (WAL mode) |
| IDs | python-ulid |
| TUI | Textual |
| Logging | structlog |
| Secrets | keyring (abstracted via `SecretProvider`) |
| DI | injector or manual constructor injection |
| Testing | pytest + pytest-asyncio |
| Lint/format | ruff |
| Types | mypy |

---

## 2. Non-Negotiable Rules

### 🔴 Rule 1: Branch Safety First

**Before ANY file operation:**
1. Run `git status -sb && git branch -a`
2. Ask user for branch confirmation
3. Wait for response
4. Only then proceed

**Never commit directly to:** `main`, `master`, `develop`, `sandbox*`, `sit*`

### 🔴 Rule 2: TDD is Mandatory

**RED → GREEN → REFACTOR cycle for EVERY change:**

1. **RED:** Write failing test first
   - Test must fail for the RIGHT reason
   - Verify failure before proceeding

2. **GREEN:** Write MINIMUM code to pass
   - No over-engineering
   - No premature optimization

3. **REFACTOR:** Improve code with tests green
   - Run tests after each change
   - Stop when clean and passing

**NEVER:**
- Write implementation before tests
- Skip tests "just this once"
- Write tests after implementation
- Commit without tests

### 🔴 Rule 3: Documentation is Mandatory

After implementation:
1. Update relevant docs in `docs/`
2. Update `CHANGES.md`
3. Verify examples/schemas/links are current

**Undocumented code is incomplete code.**

### 🔴 Rule 4: Coverage Thresholds

| Code Category | Coverage |
|---|---|
| Business Logic (services, validators, utils, rules) | 100% |
| Components / UI Logic | 80% |
| Overall Project | 80% |

**Business logic includes:** `**/services/**`, `**/validators/**`, `**/utils/**`, `**/business_rules/**`, `**/shared/**`, any file with calculations/transformations/business decisions.

---

## 3. Architecture Constraints

### A2A Transport
- Unix domain socket with OS-level peer credential auth
- Framed, length-prefixed JSON messages
- Canonical `Envelope` with: `event_type`, `schema_version`, `event_id`, `correlation_id`, `session_id`, `agent_id`, `timestamp`, `payload`
- Shared Pydantic models — no guessing from loose payloads

### Storage
- SQLite in WAL mode from day one
- **Centralized `EventWriter`** — agents send events to engine; agents do NOT write to DB directly
- Abstract repository interfaces: `SessionRepository`, `EventRepository`, `TaskRepository`, `ApprovalRepository`, `MessageRepository`
- Every approval/decision/tool invocation written to event log before/atomically with execution

### Policy
- Scopes: global → agent → session (most restrictive wins)
- `PolicyEvaluator` validates tool access independently — skills NEVER grant permissions
- Filesystem policy: exact paths + directory-prefix rules only (no globs in v1)

### Secrets
- All behind `SecretProvider` interface
- Keyring-backed by default
- No plain YAML/env secrets in config files

### Required Interfaces (define early, use everywhere)
`SessionRepository`, `EventRepository`, `TaskRepository`, `ArtifactRepository`, `MemoryRepository`, `VectorIndex`, `SecretProvider`, `ModelProvider`, `ToolExecutor`, `SkillLoader`, `PolicyEvaluator`, `ApprovalService`, `AgentRegistry`, `AgentSpawner`, `ChannelAdapter`, `WorkspaceResolver`

---

## 4. Python Development Standards

### Dependency Injection Pattern

**Constructor injection (preferred):**
```python
from typing import Protocol

class Logger(Protocol):
    def log(self, message: str) -> None: ...

class ChatService:
    def __init__(self, provider: Provider, logger: Logger):
        self.provider = provider
        self.logger = logger
```

**Use `injector` library when appropriate:**
```python
from injector import Injector, inject, Binder

def configure(binder: Binder):
    binder.bind(Provider, to=ClaudeProvider)
    binder.bind(Logger, to=ConsoleLogger)

injector = Injector([configure])
service = injector.get(ChatService)
```

### SOLID Principles

1. **Single Responsibility:** One reason to change per module/class/function
2. **Dependency Inversion:** Depend on abstractions, not concrete implementations
3. **Interface Segregation:** Small, client-specific interfaces
4. **Liskov Substitution:** Subtypes must be substitutable for base types
5. **Open/Closed:** Open for extension, closed for modification

### Import Rules

1. **Never import downward in hierarchy**
   - good: `providers → core`
   - bad: `core → providers`

2. **Use TYPE_CHECKING for forward references:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.providers import Provider
```

3. **Group imports:**
   - Standard library
   - Third-party
   - Local

### Module Organization

```
breqy/
├── domain/           # Models, enums, events, errors, IDs
├── storage/          # Repository interfaces + SQLite impls
├── a2a/              # A2A envelope, transport, server, client
├── engine/           # Event bus, writer, router, session mgr
├── agents/           # Agent runtime
├── tui/              # Textual TUI application
├── tools/            # Tool implementations
├── policy/           # PolicyEvaluator, ApprovalService
├── config/           # Config loader, settings models
├── secrets/          # SecretProvider + keyring impl
└── utils/
```

---

## 5. Worktree Workflow

**Use worktree when:**
- Work is non-trivial (multiple commits)
- Tasks are parallelized across branches
- Current workspace has unrelated local changes
- User explicitly asks for isolated execution

**Directory selection order:**
1. `.worktrees/` if exists
2. `worktrees/` if exists
3. Check `CLAUDE.md` for guidance
4. Ask user

**Required sequence:**
1. Confirm branch strategy with user
2. Verify `.gitignore` includes chosen directory
3. Create: `git worktree add <path> -b <branch-name> <start-point>`
4. `cd` into worktree
5. Run baseline validation (`pytest -q` or project quick test)
6. Report worktree path in updates

---

## 6. Testing Standards

### Test Quality

Each test must be:
1. **Isolated** — no dependencies on other tests
2. **Deterministic** — same input = same result
3. **Fast** — mock external I/O
4. **Readable** — AAA structure (Arrange-Act-Assert)
5. **Focused** — one behavior per test

### Coverage Requirements

```python
# Test categories:
# 1. Happy path — normal expected usage
# 2. Error cases — how failures are handled
# 3. Edge cases — boundaries, empty values, null
# 4. Side effects — logging, metrics, external calls
```

### Test Structure Pattern

```python
import pytest
from unittest.mock import Mock

class TestFeatureName:
    @pytest.fixture
    def mock_dependency(self):
        dep = Mock(spec=DependencyInterface)
        dep.method.return_value = "expected"
        return dep

    def test_happy_path(self, mock_dependency):
        # Arrange
        service = FeatureService(mock_dependency)
        
        # Act
        result = service.execute(valid_input)
        
        # Assert
        assert result == expected_output
        mock_dependency.method.assert_called_once()
```

---

## 7. Git Workflow

### Branch Naming

- `feat/<short-kebab>`
- `fix/<short-kebab>`
- `hotfix/<short-kebab>`
- `chore/<short-kebab>`
- `docs/<short-kebab>`
- `refactor/<short-kebab>`
- `test/<short-kebab>`

### Commit Strategy

**Minimum 2 commits per feature:**
1. `test: add test for <behavior>`
2. `feat: implement <behavior>`
3. (Optional) `refactor: improve <implementation>`

**Each commit must:**
- Have passing tests
- Build successfully
- Be deployable

### Before PR

1. All tests green
2. No skipped/disabled tests
3. Coverage thresholds met
4. Tests run fast (< 1s per test file for unit tests)

---

## 8. Domain Model Quick Reference

| Object | Owner | Notes |
|---|---|---|
| `Session` | Engine | Persistent; survives restarts |
| `Participant` | Engine | Agent or channel connected to session |
| `Agent` | Agent process | Has persona, tool perms, private memory |
| `Message` | Engine | Stored in canonical DB |
| `Event` | Engine | Append-only event log |
| `Task` | Engine | Engine owns state; agents propose updates |
| `ApprovalRequest/Decision` | Engine | Durable before execution |
| `Artifact` | Engine | Metadata in DB; content on disk |
| `Workspace` | Engine | Operational scope boundary |
| `MemoryRecord` | Engine/Agent | Global/session (engine) or agent-private |
| `Job` | Engine | Background or session-linked jobs |
| `Skill` | Loaded at invocation | File-based; injected as context, not permissions |
| `ToolInvocation` | Engine/Agent | Logged before execution |
| `PolicyRule` | Engine | Evaluated at all scopes |

---

## 9. Control Primitives

| Command | Behavior |
|---|---|
| **Stop** | Cancel active work ASAP |
| **Stop and steer** | Let current atomic step finish, then stop plan and accept new direction |
| **Steer** | Let current step complete, then update context/plan and continue |
| **Circuit break** | Hard kill all related agent processes; record emergency termination |

---

## 10. Non-Functional Priorities

1. Reliability and restart safety
2. Security and permission correctness
3. Transparency and auditability
4. Debuggability
5. Extensibility
6. Easy local setup
7. Low latency and responsiveness
8. Portability (Linux-first)
9. Testability
10. Low resource usage

---

## 11. Execution Checklists

### Before Starting Work

- [ ] Read all four instruction files (core, project, python, tdd)
- [ ] Check branch: `git status -sb && git branch -a`
- [ ] Confirm branch with user
- [ ] Create worktree if needed (non-trivial work)

### TDD Checkpoint (Before Implementation)

- [ ] Have I written the test file?
- [ ] Does the test fail for the right reason?
- [ ] Am I writing the minimum code to pass?

**If any "no": stop and return to RED.**

### Documentation Checkpoint (After Implementation)

- [ ] Did I update relevant docs in `docs/`?
- [ ] Did I document new feature/API behavior?
- [ ] Are examples/schemas current?
- [ ] Did I update `CHANGES.md`?

**If any "no": stop and update docs.**

### Final Checklist (Before Commit)

- [ ] **Branch Safety:** Correct branch (not protected trunk), user-confirmed
- [ ] **TDD Complete:** Tests written first, fail-first validated, all pass, coverage met
- [ ] **Documentation Complete:** Docs updated, `CHANGES.md` updated, links/examples validated
- [ ] **Code Quality:** Clean, maintainable, no debug leftovers, proper error handling
- [ ] **Commit Quality:** Conventional commit message, clear scope and rationale

---

## 12. Key Files to Reference

| File | Purpose |
|---|---|
| `docs/intent.md` | Why Breqy exists, guiding principles |
| `docs/prd.md` | Full product requirements |
| `docs/architecture.md` | Runtime topology and design |
| `docs/decisions.md` | Architecture decision records |
| `docs/plans/2026-03-13-breqy-slice-1.md` | Active implementation plan |
| `docs/ai_delivery_approach_v_1.md` | AI-assisted delivery lifecycle |
| `docs/shaped_task_schema.md` | Task shaping format |
| `docs/lessons_learned_schema.md` | Lessons capture format |

---

## 13. Known Risks to Watch

1. **Agent process sprawl** — enforce session-level and runtime-level process limits
2. **TUI responsiveness** — input handling must remain responsive during streaming (hard constraint)
3. **SQLite write contention** — WAL mode + centralized `EventWriter` from day one

---

## 14. Out of Scope for v1

- Cloud-native deployment as core path
- Multi-user accounts/permissions
- Rich Web UI
- Production Telegram/WhatsApp support
- MCP integration beyond extension points
- Persistent config editing from UI
- Advanced tracing/metrics stack
- Agent-local skill libraries
- Glob/wildcard pattern matching in filesystem policy

---

## 15. My Operating Mode

**When user asks me to do something:**

1. **Stop** — check branch first
2. **Ask** — confirm branch strategy
3. **Plan** — create todo list for complex tasks
4. **TDD** — write failing test first
5. **Implement** — minimum code to pass
6. **Refactor** — improve with tests green
7. **Document** — update docs and `CHANGES.md`
8. **Verify** — run tests, check coverage
9. **Commit** — conventional commits with clear messages

**When acting as Orchestrator:**

1. Read backlog and identify next eligible tasks
2. Generate shaped task envelopes
3. Route tasks to appropriate agents (Planner, Doer, Checker, Tester)
4. Collect artifacts and enforce completion gates
5. Manage branch creation and merge paths
6. Escalate blocked or looping tasks
7. Capture lessons learned

**Multi-Agent Coordination:**

- Spawn role-specific subagents (reviewer, tester) for code changes
- Iterate reviewer+tester cycles until both are clean
- Accept or decline findings based on best code quality (not speed)
- Add accepted fixes to JSONL plan with TDD steps
- Re-run reviewer/tester after fixes

**When in doubt: RED → GREEN → REFACTOR**

---

## 16. Quick Commands Reference

```bash
# Branch check (ALWAYS first)
git status -sb && git branch -a

# Create worktree
git worktree add .worktrees/feat-name -b feat/name main

# Run tests
pytest -q

# Run tests with coverage
pytest --cov=breqy --cov-report=term-missing

# Lint/format
ruff check breqy/
ruff format breqy/

# Type check
mypy breqy/

# All checks
ruff check breqy/ && pytest -q && mypy breqy/
```

---

**Remember: TDD is not about testing, it's about design.**

Writing tests first forces you to think about interfaces before implementation, write testable (and therefore better) code, create minimal focused solutions, and build confidence in your changes.

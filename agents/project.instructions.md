# Project Instructions — Breqy

## 1. What this project is

Breqy is a **Linux-first, always-on, multi-agent AI assistant** built as a local persistent runtime. It consists of three separate processes communicating over typed A2A (agent-to-agent) protocol:

- **breqy-engine** — long-running daemon that owns sessions, events, memory, task state, and policy
- **breqy agent processes** — separate processes that hold a persona, execute tools, and connect to the engine via A2A
- **breqy-tui** — a Textual TUI application that connects only to the engine, not directly to agents

The system is personal-first (local Linux desktop/VM/SSH), not cloud-native. There is no assumed cloud deployment path for v1.

Full intent: `docs/intent.md` | Full PRD: `docs/prd.md` | Architecture: `docs/architecture.md`

---

## 2. Technology stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Typing | Pydantic v2 (models, events, config) |
| Async DB | aiosqlite (SQLite with WAL mode) |
| IDs | python-ulid |
| TUI | Textual |
| Logging | structlog |
| Secrets | keyring (preferred on Linux); abstracted behind `SecretProvider` |
| DI | injector library or manual constructor injection |
| Testing | pytest + pytest-asyncio |
| Lint/format | ruff |
| Types | mypy |

All infrastructure (storage, model provider, secret provider) must be hidden behind abstract interfaces and injected via DI. No concrete implementations may be imported directly by business logic.

---

## 3. Repository layout

```
breqy/                    # Main Python package
  domain/                 # Domain models, enums, events, errors, ID generation
  storage/                # Abstract repository interfaces + SQLite implementations
  a2a/                    # A2A transport: envelope, Unix socket client/server
  engine/                 # Engine daemon: event bus, writer, router, session mgr
  agents/                 # Agent runtime: runner, memory, tool executor
  tui/                    # Textual TUI application
  tools/                  # Tool implementations (shell, fs, memory, etc.)
  policy/                 # PolicyEvaluator, ApprovalService, rule models
  config/                 # Config loader, agent manifest, settings models
  secrets/                # SecretProvider interface + keyring impl

agents/                   # Agent definition folders (persona, manifest, etc.)
  breqy/                  # Default Breqy agent
    agent.yaml
    persona.md

skills/                   # Global skill packs (instructions + optional scripts)
system/                   # Orchestration agents and templates
docs/                     # PRD, architecture, decisions, plans
tests/                    # unit/, integration/, tui/
scripts/                  # Dev tooling and guardian scripts
.breqy/                   # Runtime data: guardian logs, lessons, etc.
```

Detailed file-level responsibilities are in `docs/plans/2026-03-13-breqy-slice-1.md`.

---

## 4. Current implementation scope — Slice 1

**Slice 1 is the active implementation target.** Do not add Slice 2 features unless explicitly instructed.

### Slice 1 must deliver

- Engine daemon with session persistence
- Default `breqy` agent process connecting via A2A
- TUI client (Textual) connecting only to engine
- Persistent sessions: create and resume
- Streaming chat
- Shell tool and filesystem tool
- Inline approvals
- Visible task list
- Control primitives: stop, stop-and-steer, steer, circuit-break
- Typed A2A event schemas for all core runtime events

### Slice 2 (do NOT implement yet)

Memory retrieval and promotion, SSH tool, agent delegation/handoff, Docker inspection, artifact tracking.

---

## 5. Architecture constraints — mandatory

These are hard constraints, not preferences.

### A2A transport
- Unix domain socket with OS-level peer credential auth for local mode
- Framed, length-prefixed JSON messages
- All messages use a canonical typed `Envelope` with fields: `event_type`, `schema_version`, `event_id`, `correlation_id`, `session_id`, `agent_id`, `timestamp`, `payload`
- Shared schema models (Pydantic) must be used by engine, agents, and TUI — no guessing from loosely shaped payloads

### Storage
- SQLite in WAL mode from day one
- **Centralized event writer**: engine has one `EventWriter` component that agents send events to; agents do not write to the DB directly. This prevents SQLite write contention.
- All storage behind `SessionRepository`, `EventRepository`, `TaskRepository`, `ApprovalRepository`, `MessageRepository` abstract interfaces
- Every approval request, decision, and tool invocation must be written to the event log before or atomically with execution

### Policy
- Policy scopes: global → agent → session (most restrictive wins)
- `PolicyEvaluator` must validate tool access independently of skill metadata — skills never grant permissions
- Filesystem policy uses exact paths and directory-prefix rules only (no globs in v1)

### Secrets
- All secrets behind `SecretProvider` interface
- Keyring-backed by default; no plain YAML/env secrets in normal config files

### Interfaces
Define early and use everywhere:
`SessionRepository`, `EventRepository`, `TaskRepository`, `ArtifactRepository`, `MemoryRepository`, `VectorIndex`, `SecretProvider`, `ModelProvider`, `ToolExecutor`, `SkillLoader`, `PolicyEvaluator`, `ApprovalService`, `AgentRegistry`, `AgentSpawner`, `ChannelAdapter`, `WorkspaceResolver`

---

## 6. Domain model — key objects

| Object | Owner | Notes |
|---|---|---|
| `Session` | Engine | Persistent; survives restarts |
| `Participant` | Engine | Agent or channel connected to a session |
| `Agent` | Agent process | Has persona, tool perms, private memory |
| `Message` | Engine | Stored in canonical DB |
| `Event` | Engine | Append-only event log |
| `Task` | Engine | Engine owns canonical state; agents propose updates |
| `ApprovalRequest` / `ApprovalDecision` | Engine | Linked to tool invocations; durable before execution |
| `Artifact` | Engine | Metadata in DB; file content on disk |
| `Workspace` | Engine | Operational scope boundary for a session |
| `MemoryRecord` | Engine/Agent | Global/session owned by engine; agent-private owned by agent |
| `Job` | Engine | Background or session-linked jobs |
| `Skill` | Loaded at invocation | File-based; injected as structured context, not permissions |
| `ToolInvocation` | Engine/Agent | Logged before execution |
| `PolicyRule` | Engine | Evaluated by `PolicyEvaluator` at all scopes |

---

## 7. Memory architecture

| Layer | Owner | Purpose |
|---|---|---|
| Global memory | Engine | Durable profile, facts, promoted lessons |
| Session memory | Engine | Thread continuity, working memory, task state |
| Agent-private | Agent process | Agent preferences, local retrieval, private notes |

Promotion from session → global requires explicit agent proposal plus user approval (or automatic only if autonomy policy allows). Memory access is always tool-mediated and permissioned.

---

## 8. Configuration

- File-only in v1; runtime changes are temporary session/autonomy adjustments only
- Markdown for long-form instructions (persona, skill instructions)
- YAML for manifests and structured config (agent.yaml, policy rules)
- Environment variables and secrets never hardcoded — always use `SecretProvider`
- Always maintain a `.env.sample` alongside any `.env` usage

---

## 9. Agent process model

Each agent:
- Runs as a separate OS process
- Has a configured port
- Connects and registers to engine via A2A on startup
- Executes tools within its granted permissions
- Maintains agent-private memory
- Proposes task updates and memory writes to engine

Agent definition lives in `agents/<agent-id>/`:
- `agent.yaml` — id, name, port, model prefs, tool perms, skill perms, memory config, autonomy policy, log config
- `persona.md` — system prompt / persona instructions

Dynamic (ephemeral) agents may be generated from templates at runtime and optionally promoted to persistent agents.

---

## 10. TUI requirements

- Built with Textual
- Connects only to the engine (never directly to agents)
- Renders from typed event contracts — never guesses from loosely shaped payloads
- Must remain input-responsive during streaming and tool output
- Must display: sessions list, active session/chat, agent participation, task/todo list, inline approvals, tool actions, background job status, logs/events view
- Core streamed events it must render from typed contracts: `MessageEvent`, `TaskEvent`, `ApprovalEvent`, `ToolInvocationEvent`, `ControlEvent`

A `ToolInvocationEvent` must include at minimum: event_id, session_id, task_id (if any), agent_id, tool_name, invocation_id, status, timestamps, approval_state (when relevant), human-readable summary, structured args reference, result/error reference.

---

## 11. Control primitives

| Command | Behavior |
|---|---|
| Stop | Cancel active work as soon as possible |
| Stop and steer | Let current atomic step finish safely, then stop plan and accept new direction |
| Steer | Let current step complete, then update context/plan and continue |
| Circuit break | Hard kill all related agent processes immediately; record emergency termination |

---

## 12. Non-functional priorities (in order)

1. Reliability and restart safety
2. Security and permission correctness
3. Transparency and auditability
4. Debuggability
5. Extensibility
6. Easy local setup
7. Low latency and responsiveness
8. Portability (Linux-first, Windows as fast follower)
9. Testability
10. Low resource usage

---

## 13. Known risks to watch

- **Agent process sprawl**: enforce session-level and runtime-level process limits from the start
- **TUI responsiveness**: input handling must remain responsive during streaming; treat this as a hard constraint
- **SQLite write contention**: WAL mode + centralized `EventWriter` from day one; agents must not compete for DB writes

---

## 14. What is out of scope for v1

- Cloud-native deployment as a core path
- Multi-user accounts and permissions
- Rich Web UI
- Production Telegram/WhatsApp support
- MCP integration beyond extension points
- Persistent config editing from UI
- Advanced tracing/metrics stack
- Agent-local skill libraries
- Glob/wildcard pattern matching in filesystem policy

---

## 15. Delivery and AI workflow

Work follows the AI-assisted delivery approach in `docs/ai_delivery_approach_v_1.md`. Key points:

- Shape tasks before implementation; see `docs/shaped_task_schema.md`
- One role writes production code at a time
- Checker must be independent from Doer (different model/context at minimum)
- Tasks are done only when: implementation exists, checker findings resolved, CI passes, coverage thresholds met, lessons captured, human approves merge
- Lessons go to `.breqy/lessons/<task-id>.yaml` or `ai-artifacts/<task-id>/lessons.yaml`
- Implementation plan is `docs/plans/2026-03-13-breqy-slice-1.md`

---

## 16. Worktree usage standard

For non-trivial, parallel, or risky work, prefer an isolated git worktree instead of reusing the current workspace.

Use this order to choose location:
1. `.worktrees/` (preferred when present)
2. `worktrees/` (fallback when present)
3. `CLAUDE.md` guidance (if defined)
4. ask the user

Required controls:
- confirm branch strategy with the user before creating worktree/branch
- ensure `.gitignore` contains `.worktrees/` or `worktrees/` before creating local worktrees
- create with `git worktree add <path> -b <branch> <start-point>`
- run baseline validation in the new worktree before implementation
- report the worktree path in status updates and final handoff

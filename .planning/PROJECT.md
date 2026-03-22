# Breqy

## What This Is

Breqy is a Linux-first, always-running, multi-agent assistant platform with a daemon engine, separable agent processes, modular channel adapters, persistent sessions, layered memory, built-in tool execution, and policy-driven approvals. The first client is a Textual TUI application that connects to the engine. It is designed as a personal-first local runtime that can evolve into a household or broader multi-user platform without cloud dependency.

## Core Value

A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Engine runs as an always-on daemon owning sessions, events, and policy
- [ ] TUI connects to running engine and streams session events
- [ ] Persistent sessions survive restarts and disconnects
- [ ] Streaming chat with visible task list
- [ ] Shell and filesystem tool execution via policy gates
- [ ] Inline approvals for tool actions
- [ ] Stop, stop-and-steer, steer, and circuit-break control primitives
- [ ] Canonical typed A2A event schemas shared across engine, agents, and TUI
- [ ] SQLite persistence with WAL mode and centralized event writer
- [ ] Default `breqy` agent with persona, tool permissions, and autonomy policy
- [ ] Policy evaluator with layered rule resolution (global → agent → session, most restrictive wins)
- [ ] Filesystem path-based policy (read/write/delete/execute, whitelist/approve/blacklist)
- [ ] UNIX domain socket transport with OS-level peer credential checks
- [ ] Agent definitions as file-based source-of-truth folders
- [ ] Secrets abstracted behind SecretProvider interface (keyring-backed)
- [ ] All five orchestrator runner auth flows (Copilot device flow, Codex device flow, Claude PKCE, Gemini device flow, Qwen API key)
- [ ] Runner auth panel in TUI (status table, inline auth flow, OSC8 links, masked key input)

### Out of Scope

- Cloud-native deployment as a core path — local-first is the principle
- Multi-user accounts and permissions — personal-first v1
- Rich Web UI — TUI first
- Production-grade Telegram/WhatsApp support — future channels
- MCP integration beyond extension points — future work
- Persistent config editing from UI — file-based config only in v1
- Advanced tracing/metrics stack — structlog + TUI event view sufficient for v1
- SSH tool — Slice 2
- Agent delegation/handoff depth — Slice 2
- Docker inspection workflows — Slice 2
- Memory retrieval/promotion automation expansion — Slice 2
- Glob/wildcard path matching in filesystem policy — exact paths and directory-prefix only in v1
- Windows support — fast follower, not v1 core

## Context

- **Existing docs:** Full PRD (`docs/prd.md`), architecture (`docs/architecture.md`), intent (`docs/intent.md`), and a detailed Slice 1 implementation plan (`docs/plans/2026-03-13-breqy-slice-1.md`) exist. These are the source of truth for requirements and design decisions.
- **Tech stack decided:** Python 3.12+, pydantic, aiosqlite, textual, structlog, python-ulid, keyring, pytest/pytest-asyncio, ruff, mypy.
- **Architecture:** Engine ↔ Agents ↔ TUI connected via typed JSON-over-UNIX-socket A2A protocol. SQLite (WAL mode) for canonical state. Centralized event writer prevents write contention.
- **Delivery model:** Vertical slices. Slice 1 is the active target (engine + default agent + TUI + shell/fs tools + approvals + controls). Slice 2 adds memory, SSH, delegation, Docker.
- **Existing partial implementation:** Some orchestrator code and TUI scaffolding exists in `system/orchestrator/` — this is the prior system orchestrator, not the Breqy runtime itself. The core `breqy/` package is the build target.

## Constraints

- **Tech stack:** Python 3.12+, pydantic v2, aiosqlite, textual — already decided, no alternatives
- **Platform:** Linux-first for v1; avoid design choices that block Windows later
- **Auth:** Credentials must be stored in OS keyring only — never written to plain YAML or `.env` by the system
- **Storage:** SQLite WAL mode with centralized event writer — must not let agents write directly to DB
- **Transport:** UNIX domain socket with OS-level peer credentials for local-mode v1
- **Policy:** Most restrictive rule wins across global/agent/session scopes
- **Config:** File-only in v1 (YAML for manifests, Markdown for instructions); runtime changes are temporary only
- **TDD:** Test-driven development enforced — tests written before implementation per project AGENTS.md

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.12 monorepo | Consistent tooling, type safety with pydantic v2, async-first | — Pending |
| UNIX domain socket transport | Local-first, OS-level peer auth, no network exposure by default | — Pending |
| SQLite WAL + centralized writer | Prevents write contention; agents queue events non-blocking | — Pending |
| Textual for TUI | Rich async TUI, streaming-capable, Python-native | — Pending |
| A2A typed event envelopes | Shared schema prevents heuristic payload interpretation across engine/agents/TUI | — Pending |
| Keyring-backed SecretProvider | Credentials never touch plain config files | — Pending |
| Layered policy (most restrictive wins) | Predictable, auditable permission resolution | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-22 after initialization*

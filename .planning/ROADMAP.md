# Roadmap: Breqy

**Milestone:** M1 — Slice 1 Full Build
**Granularity:** Fine (10 phases)
**Coverage:** 57/57 requirements mapped ✓
**Created:** 2026-03-22

---

## Phases

- [x] **Phase 1: Domain Foundation** — ULID IDs, enums, core models, typed events, domain errors
- [x] **Phase 2: Storage Layer** — Repository interfaces, SQLite management, schema/migrations, SQLite impls, centralized event writer
- [ ] **Phase 3: Config, Secrets & A2A Protocol** — Config loader, dataclasses, SecretProvider/Keyring, A2A envelope, UNIX socket transport, server, client, round-trip contracts
- [ ] **Phase 4: Policy & Approvals** — PolicyEvaluator, filesystem policy, tool permission rules, autonomy levels, ApprovalService, session-scoped grants
- [ ] **Phase 5: Engine Runtime** — Daemon startup/shutdown, internal event bus, session manager, agent registry, agent spawner, restart restore
- [ ] **Phase 6: Tools** — ToolExecutor/ToolResult/ToolRegistry, ShellTool, FilesystemTool, MCP client, memory tool
- [ ] **Phase 7: Memory** — Session memory, global memory, agent-private memory, tool-mediated access, promotion flow
- [ ] **Phase 8: Agent Runtime & Auth** — Config loader, runtime loop, breqy agent definition, model provider, 5 auth providers, CredentialStore, skills loader
- [ ] **Phase 9: Sessions & Control** — Restart survival, participant tracking, 4 control primitives, canonical task state, workspace scoping
- [ ] **Phase 10: TUI Client** — Session list, chat streaming, typed event rendering, task list, approval widget, control bar, agent status, tool widget, auth panel, logs, slash commands, model view, originator header

---

## Phase Details

### Phase 1: Domain Foundation

**Goal**: The shared vocabulary of the entire system exists — all domain objects, enums, typed events, and error types are defined and importable by every other layer.

**Depends on**: Nothing (first phase)

**Requirements**: DOM-01, DOM-02, DOM-03, DOM-04, DOM-05

**Success Criteria** (what must be TRUE):
1. ULID-prefixed IDs can be generated for any domain object type (e.g., `ses_01ARZ3NDEKTSV4RRFFQ69G5FAV`)
2. All enumerations (`SessionStatus`, `TaskStatus`, `EventType`, `MessageRole`, `ToolStatus`, `ApprovalStatus`, `PolicyScope`, `FilesystemOperation`, `AutonomyLevel`) are importable and have their full value set
3. All core domain models (`Session`, `Message`, `Participant`, `Task`, `ToolInvocation`, `ApprovalRequest`, `ApprovalDecision`, `PolicyRule`, `Agent`) can be instantiated and serialized via pydantic
4. All 11 typed event schemas (`MessageSentEvent`, `MessageChunkEvent`, `TaskUpdatedEvent`, `ToolInvocationStartedEvent`, `ToolInvocationCompletedEvent`, `ToolOutputChunkEvent`, `ApprovalRequestedEvent`, `ApprovalDecidedEvent`, `ControlEvent`, `AgentLifecycleEvent`, `SessionCreatedEvent`) are instantiable and carry required fields
5. All 8 domain error types (`BreqyError`, `SessionNotFoundError`, `AgentNotFoundError`, `PolicyDeniedError`, `ApprovalRequiredError`, `ToolExecutionError`, `AgentSpawnError`, `TransportError`) can be raised and caught

**Plans**: TBD

---

### Phase 2: Storage Layer

**Goal**: Persistent state storage is operational — the engine can durably record sessions, messages, events, tasks, approvals, and tool invocations via injectable repository abstractions backed by SQLite.

**Depends on**: Phase 1 (domain models)

**Requirements**: STR-01, STR-02, STR-03, STR-04, STR-05

**Success Criteria** (what must be TRUE):
1. Abstract repository interfaces (`SessionRepository`, `MessageRepository`, `EventRepository`, `TaskRepository`, `ApprovalRepository`) can be injected and used without knowing the underlying storage backend
2. SQLite connections open with WAL mode, foreign keys enabled, and busy timeout configured; a second writer does not block readers
3. All Slice 1 DDL tables (`sessions`, `messages`, `events`, `tasks`, `tool_invocations`, `approval_requests`, `approval_decisions`, `participants`) are created idempotently on startup — running migrations twice does not fail
4. SQLite repository implementations correctly persist and retrieve all domain objects by ID; round-trip (save → load) returns identical structs
5. The centralized event writer accepts events queued from multiple async producers and writes them sequentially without data races; agents attempting to write directly to DB are rejected

**Plans**: TBD

---

### Phase 3: Config, Secrets & A2A Protocol

**Goal**: The communication backbone and configuration infrastructure is in place — the engine and agents share a canonical typed message protocol over UNIX sockets, and all configuration and secrets are loaded via structured, safe interfaces.

**Depends on**: Phase 1 (domain event types), Phase 2 (storage for session IDs)

**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, A2A-01, A2A-02, A2A-03, A2A-04, A2A-05

**Success Criteria** (what must be TRUE):
1. YAML manifests and Markdown instruction files load into validated `EngineConfig` and `AgentConfig` dataclasses; invalid config raises a descriptive error at load time, not at runtime
2. `SecretProvider` ABC and `KeyringProvider` implementation can store and retrieve credentials from the OS keyring under namespaced keys (`breqy/<provider>`); no credential ever appears in a plain file
3. Runtime config changes do not persist — a restart returns to file-based values
4. An A2A envelope (with event type, schema version, event ID, correlation ID, session ID, agent ID, timestamps, payload) serializes to JSON and deserializes back to an identical struct (round-trip guaranteed)
5. Engine-side A2A server accepts a TUI or agent connection over a UNIX domain socket and routes typed frames to session subscribers; agent-side A2A client connects, sends a typed frame, and receives a typed response — full duplex exchange completes without error

**Plans**: TBD

---

### Phase 4: Policy & Approvals

**Goal**: The permission system is operational — every tool invocation and filesystem operation is evaluated against a layered rule set before execution, and approval requests are routed, recorded, and honoured.

**Depends on**: Phase 1 (domain policy types), Phase 2 (approval persistence), Phase 3 (config for rule definitions)

**Requirements**: POL-01, POL-02, POL-03, POL-04, POL-05, POL-06

**Success Criteria** (what must be TRUE):
1. `PolicyEvaluator` resolves rules across global → agent → session scopes; a more-restrictive session rule overrides a permissive global rule for the same resource
2. Filesystem policy blocks a `delete` operation on a blacklisted path, requires an approval for an approval-required path, and permits a whitelisted read — all using exact-path and directory-prefix matching only
3. Tool permission rules correctly deny a tool not allowed at the agent scope even when the global policy permits it
4. Autonomy level (`assistant` / `supervised` / `autonomous` / `privileged`) is configurable per agent and read correctly from agent config; a lower-autonomy agent triggers more approval gates than a higher-autonomy one
5. `ApprovalService` creates an approval request, records an `approved` or `denied` decision, and respects a session-scoped "approve for rest of session" grant so subsequent identical tool calls are auto-approved without another prompt

**Plans**: TBD

---

### Phase 5: Engine Runtime

**Goal**: The engine daemon is running, connected, and resilient — it binds to the UNIX socket, manages session lifecycle, tracks agents, spawns subprocesses, and survives restarts by restoring prior state from the database.

**Depends on**: Phase 2 (storage for session/agent state), Phase 3 (A2A server, config), Phase 4 (policy evaluation)

**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06

**Success Criteria** (what must be TRUE):
1. `breqy engine start` launches the daemon, binds to the configured UNIX socket path, and a `kill -SIGTERM <pid>` shuts it down cleanly (socket file removed, in-flight sessions flushed)
2. Internal async event bus delivers a published event to all registered subscribers within the same process; an unsubscribed handler does not receive the event
3. Session manager creates a new session (returns a session ID), resumes an existing session by ID (returns its prior state), and lists all sessions with their current status
4. Agent registry tracks which agents are connected to which sessions; a disconnected agent is removed from the registry
5. Agent spawner starts an agent subprocess from an agent config directory, the agent registers with the engine, and the spawner can terminate it; a failed spawn is recorded and does not crash the engine
6. On engine restart, all sessions that were active at shutdown are restored from DB — their tasks, messages, and participants are available immediately after startup without requiring any TUI action

**Plans**: TBD

---

### Phase 6: Tools

**Goal**: The engine can execute approved shell commands and filesystem operations, and external MCP tool servers can be connected — all tool calls go through policy gates and stream output back to the session.

**Depends on**: Phase 1 (domain tool types), Phase 4 (policy evaluation for gating), Phase 5 (engine event bus for streaming)

**Requirements**: TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05, TOOL-06

**Success Criteria** (what must be TRUE):
1. `ToolExecutor` ABC and `ToolResult` define the tool contract; any class that implements the ABC and is registered in `ToolRegistry` can be looked up by name and invoked
2. `ShellTool` executes a shell command as a subprocess; stdout/stderr chunks are streamed as `ToolOutputChunkEvent`s; the call is gated by policy and blocked if the command is denied
3. `FilesystemTool` reads, writes, edits, and deletes files; each operation is evaluated by filesystem policy — a write to a blacklisted path raises `PolicyDeniedError`, a write to an approval-required path suspends until approved
4. MCP client connects to a configured MCP server and exposes the server's tool list via `ToolRegistry`; an agent can invoke an MCP-backed tool the same way it invokes a native tool
5. Memory tool (MCP-backed) resolves session, global, and agent-private memory domains and returns records scoped to the requesting agent and session

**Plans**: TBD

---

### Phase 7: Memory

**Goal**: The system maintains persistent, scoped memory — sessions accumulate continuity context, global memory holds durable facts, and agents keep private working state — all accessed through a permissioned, tool-mediated interface.

**Depends on**: Phase 2 (storage), Phase 6 (MCP memory tool)

**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05

**Success Criteria** (what must be TRUE):
1. Session memory stores thread continuity, task state references, approval history, and artifact refs; querying session memory after a restart returns the same records that were present before shutdown
2. Global memory stores durable profile facts and promoted lessons; a fact written to global memory in one session is readable in a different session
3. Agent-private memory is isolated — memory written by Agent A is not readable by Agent B even within the same session
4. Memory access requires the agent to call the memory tool (not direct DB access); an agent attempting direct DB access is rejected; the tool respects session and permission scoping
5. An agent proposes a memory promotion (session → global); the promotion is surfaced as an approval request; once approved (or auto-committed under `autonomous`/`privileged` policy), the fact appears in global memory

**Plans**: TBD

---

### Phase 8: Agent Runtime & Auth

**Goal**: The default `breqy` agent is fully operational — it loads from a file-based manifest, registers with the engine, runs its inference loop, invokes tools, and can authenticate to all five supported model providers with credentials safely stored in the OS keyring.

**Depends on**: Phase 3 (A2A client, config, secrets), Phase 5 (engine spawner/registry), Phase 6 (tool registry)

**Requirements**: AGT-01, AGT-02, AGT-03, AGT-04, AGT-05, AGT-06, AGT-07, AGT-08, AGT-09, AGT-10, AGT-11

**Success Criteria** (what must be TRUE):
1. Agent config loader reads `agent.yaml` and `persona.md` from an agent directory and produces a validated `AgentConfig`; a missing required field raises a descriptive error before the agent starts
2. The `breqy` agent definition directory exists with `agent.yaml` and `persona.md`; the persona reflects the defined traits (sharp, calm, high-agency, slightly disruptive, trustworthy)
3. Agent runtime loop connects to the engine via A2A client on startup, registers, receives an incoming message event, calls a tool, and streams a response — the full round-trip completes without manual intervention
4. Model provider abstraction streams tokens/chunks back to the caller; a tool-call delta from the model is translated into a `ToolInvocationStartedEvent` on the bus
5. Each auth provider completes its respective flow (GitHub Copilot: device flow with URL + user code; Codex: OpenAI device flow; Claude: PKCE URL displayed + code paste; Gemini: device flow; Qwen: masked API key input); on completion, credentials are stored under `breqy/<provider>` in the OS keyring and never written to any file
6. `CredentialStore` retrieves a credential from the keyring by provider name and injects it into the appropriate runner; no credential is accessible from plain config or environment variables
7. Skills loader reads skill manifests from disk, validates that all required tools are permitted in the agent's config, and refuses to load a skill whose required tools are missing

**Plans**: TBD

---

### Phase 9: Sessions & Control

**Goal**: Sessions are durable and controllable — they survive restarts, track all participants, and respond immediately to user control signals (stop, stop-and-steer, steer, circuit-break) while maintaining canonical task state and workspace scoping.

**Depends on**: Phase 5 (engine, session manager), Phase 8 (agent runtime for agent lifecycle signals)

**Requirements**: SES-01, SES-02, SES-03, SES-04, SES-05, SES-06, SES-07, SES-08

**Success Criteria** (what must be TRUE):
1. A TUI reconnect after engine restart resumes the same session with complete message history, task list, and participant record — no data is lost between disconnect and reconnect
2. Session participant record shows the primary agent and any subagents with join/leave timestamps; a disconnected agent's leave timestamp is recorded
3. Stop control cancels active agent work within one event cycle; the session transitions to an idle state and the user can send a new message immediately
4. Stop-and-steer lets the current atomic tool step complete, then halts the plan; a new direction sent by the user becomes the new active plan
5. Steer updates the active plan context mid-flight without stopping the agent; the agent acknowledges the new context in its next response
6. Circuit-break hard-kills all agent subprocesses for the session immediately; the session record shows `circuit_broken` status and the emergency termination timestamp
7. Task state is owned by the engine; an agent proposes a task update, the engine validates and persists it, and the canonical state is what the TUI displays — an agent cannot unilaterally overwrite engine-owned state
8. A workspace path can be attached to a session; the agent's default filesystem operations are scoped to that workspace unless policy explicitly permits paths outside it

**Plans**: TBD

---

### Phase 10: TUI Client

**Goal**: The Textual TUI provides the full user experience — session browsing, real-time chat, live task and tool status, inline approvals, control actions, runner authentication, structured event logs, and slash commands — all driven by typed A2A events with no heuristic payload parsing.

**Depends on**: Phase 3 (A2A client), Phase 5 (engine live), Phase 8 (agent live), Phase 9 (sessions and controls)

**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-05, TUI-06, TUI-07, TUI-08, TUI-09, TUI-10, TUI-11, TUI-12, TUI-13

**Success Criteria** (what must be TRUE):
1. Session list screen shows all active sessions with status; a user can select one to resume or press a key to create a new session — both transitions navigate to the chat screen
2. Chat screen streams message chunks in real time as they arrive from the engine; a 50-token response is visible incrementally (no waiting for full response)
3. All typed events render from their schemas without any string-matching heuristics: message events render as chat bubbles, task events update the task widget, tool events update the tool widget, approval events surface the approval prompt, control events update the control bar state
4. Task list widget updates live as the agent proposes and updates tasks; the current task is highlighted and todo items are listed; completing a task removes it from the active list
5. Inline approval prompt appears when an `ApprovalRequestedEvent` arrives; the user can approve, deny, or "approve for session"; the decision is sent back to the engine and the agent continues (or stops) accordingly
6. Control bar buttons (Stop, Stop-and-Steer, Steer, Circuit-Break) send the corresponding `ControlEvent` to the engine; each button reflects the appropriate disabled/active state based on session status
7. Runner auth panel shows all configured providers with their auth status (authenticated / needs auth / error); triggering GitHub Copilot auth shows device code + URL as OSC8 link; Claude PKCE shows URL + paste field; Qwen shows masked API key input — on success the status updates to authenticated
8. Logs/events view shows structured engine and agent events with level, source, and timestamp; events can be filtered by type
9. Slash commands (e.g., `/help`, `/clear`, `/stop`) are recognized in the message input and dispatched as structured commands — unrecognized slash commands show an error hint, not a plain message send
10. Provider/model selection view lists available providers and models; selecting a model updates the active model for the session

**Plans**: TBD

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Domain Foundation | 4/4 | Complete | 2026-03-22 |
| 2. Storage Layer | 4/4 | Complete | 2026-03-22 |
| 3. Config, Secrets & A2A Protocol | 0/? | Not started | - |
| 4. Policy & Approvals | 0/? | Not started | - |
| 5. Engine Runtime | 0/? | Not started | - |
| 6. Tools | 0/? | Not started | - |
| 7. Memory | 0/? | Not started | - |
| 8. Agent Runtime & Auth | 0/? | Not started | - |
| 9. Sessions & Control | 0/? | Not started | - |
| 10. TUI Client | 0/? | Not started | - |

---

## Coverage Map

| Requirement | Phase |
|-------------|-------|
| DOM-01 | Phase 1 |
| DOM-02 | Phase 1 |
| DOM-03 | Phase 1 |
| DOM-04 | Phase 1 |
| DOM-05 | Phase 1 |
| STR-01 | Phase 2 |
| STR-02 | Phase 2 |
| STR-03 | Phase 2 |
| STR-04 | Phase 2 |
| STR-05 | Phase 2 |
| CFG-01 | Phase 3 |
| CFG-02 | Phase 3 |
| CFG-03 | Phase 3 |
| CFG-04 | Phase 3 |
| A2A-01 | Phase 3 |
| A2A-02 | Phase 3 |
| A2A-03 | Phase 3 |
| A2A-04 | Phase 3 |
| A2A-05 | Phase 3 |
| POL-01 | Phase 4 |
| POL-02 | Phase 4 |
| POL-03 | Phase 4 |
| POL-04 | Phase 4 |
| POL-05 | Phase 4 |
| POL-06 | Phase 4 |
| ENG-01 | Phase 5 |
| ENG-02 | Phase 5 |
| ENG-03 | Phase 5 |
| ENG-04 | Phase 5 |
| ENG-05 | Phase 5 |
| ENG-06 | Phase 5 |
| TOOL-01 | Phase 6 |
| TOOL-02 | Phase 6 |
| TOOL-03 | Phase 6 |
| TOOL-04 | Phase 6 |
| TOOL-05 | Phase 6 |
| TOOL-06 | Phase 6 |
| MEM-01 | Phase 7 |
| MEM-02 | Phase 7 |
| MEM-03 | Phase 7 |
| MEM-04 | Phase 7 |
| MEM-05 | Phase 7 |
| AGT-01 | Phase 8 |
| AGT-02 | Phase 8 |
| AGT-03 | Phase 8 |
| AGT-04 | Phase 8 |
| AGT-05 | Phase 8 |
| AGT-06 | Phase 8 |
| AGT-07 | Phase 8 |
| AGT-08 | Phase 8 |
| AGT-09 | Phase 8 |
| AGT-10 | Phase 8 |
| AGT-11 | Phase 8 |
| SES-01 | Phase 9 |
| SES-02 | Phase 9 |
| SES-03 | Phase 9 |
| SES-04 | Phase 9 |
| SES-05 | Phase 9 |
| SES-06 | Phase 9 |
| SES-07 | Phase 9 |
| SES-08 | Phase 9 |
| TUI-01 | Phase 10 |
| TUI-02 | Phase 10 |
| TUI-03 | Phase 10 |
| TUI-04 | Phase 10 |
| TUI-05 | Phase 10 |
| TUI-06 | Phase 10 |
| TUI-07 | Phase 10 |
| TUI-08 | Phase 10 |
| TUI-09 | Phase 10 |
| TUI-10 | Phase 10 |
| TUI-11 | Phase 10 |
| TUI-12 | Phase 10 |
| TUI-13 | Phase 10 |

**Total mapped: 57/57 ✓**

---
*Roadmap created: 2026-03-22*
*Last updated: 2026-03-22 after initial creation*

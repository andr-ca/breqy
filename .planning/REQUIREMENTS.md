# Requirements: Breqy

**Defined:** 2026-03-22
**Core Value:** A reliable, always-on engine that accepts connections from a TUI, maintains persistent sessions across restarts, and lets the default agent perform approved Linux admin and filesystem tasks with full user visibility and control.

## v1 Requirements

### Domain Models

- [ ] **DOM-01**: System has ULID-based prefixed ID generation for all domain objects
- [ ] **DOM-02**: System defines SessionStatus, TaskStatus, EventType, MessageRole, ToolStatus, ApprovalStatus, PolicyScope, FilesystemOperation, AutonomyLevel enums
- [ ] **DOM-03**: System has core domain models: Session, Message, Participant, Task, ToolInvocation, ApprovalRequest, ApprovalDecision, PolicyRule, Agent
- [ ] **DOM-04**: System has typed event schemas for all core event types: MessageSentEvent, MessageChunkEvent, TaskUpdatedEvent, ToolInvocationStartedEvent, ToolInvocationCompletedEvent, ToolOutputChunkEvent, ApprovalRequestedEvent, ApprovalDecidedEvent, ControlEvent, AgentLifecycleEvent, SessionCreatedEvent
- [ ] **DOM-05**: System has domain error types: BreqyError, SessionNotFoundError, AgentNotFoundError, PolicyDeniedError, ApprovalRequiredError, ToolExecutionError, AgentSpawnError, TransportError

### Storage

- [ ] **STR-01**: System has abstract repository interfaces (SessionRepository, MessageRepository, EventRepository, TaskRepository, ApprovalRepository) injectable via DI
- [ ] **STR-02**: System has SQLite connection management with WAL mode, foreign keys, and busy timeout
- [ ] **STR-03**: System has SQLite schema DDL for all Slice 1 tables (sessions, messages, events, tasks, tool_invocations, approval_requests, approval_decisions, participants) with idempotent migrations
- [ ] **STR-04**: System has SQLite implementations of all repository interfaces
- [ ] **STR-05**: Engine uses a centralized event writer that accepts queued events from agents and writes them sequentially — agents must not write directly to DB

### A2A Protocol

- [ ] **A2A-01**: System has canonical typed A2A envelope with required fields: event type, schema version, event ID, correlation ID, session ID, agent ID, timestamps, payload
- [ ] **A2A-02**: System has async UNIX domain socket transport (framed read/write)
- [ ] **A2A-03**: Engine-side A2A server accepts connections, routes events to session subscribers
- [ ] **A2A-04**: Agent/TUI-side A2A client connects to engine socket, sends and receives typed frames
- [ ] **A2A-05**: A2A typed contracts are round-trippable (serialize → deserialize → identical struct)

### Engine Runtime

- [ ] **ENG-01**: Engine daemon starts, binds to UNIX socket, and handles SIGTERM/SIGINT gracefully
- [ ] **ENG-02**: Engine has in-process async event bus for internal pub/sub routing
- [ ] **ENG-03**: Engine session manager creates new sessions, resumes existing sessions by ID, and lists active sessions
- [ ] **ENG-04**: Engine agent registry tracks connected agents by ID and session
- [ ] **ENG-05**: Engine agent spawner starts agent subprocesses from agent config and manages their lifecycle
- [ ] **ENG-06**: Engine restores all active sessions from DB on startup (restart survival)

### Policy & Approvals

- [ ] **POL-01**: PolicyEvaluator resolves rules across global → agent → session scopes; most restrictive rule wins
- [ ] **POL-02**: Filesystem policy enforces path-based rules per operation class (read/write/delete/execute) with whitelist / approval-required / blacklist modes using exact paths and directory-prefix matching
- [ ] **POL-03**: Tool permission rules allow/deny tool access at global/agent/session scope
- [ ] **POL-04**: Autonomy level is configurable per agent (assistant/supervised/autonomous/privileged)
- [ ] **POL-05**: ApprovalService handles approval lifecycle: create request, record decision, check session-scoped grants
- [ ] **POL-06**: Session-scoped approval grants allow "approve for rest of session" without repeated prompts

### Tools

- [ ] **TOOL-01**: ToolExecutor ABC + ToolResult defines the tool execution contract
- [ ] **TOOL-02**: ToolRegistry registers and looks up tool implementations by name
- [ ] **TOOL-03**: ShellTool executes shell commands as subprocesses with approval gating and output streaming
- [ ] **TOOL-04**: FilesystemTool provides read/write/edit/delete operations governed by filesystem policy
- [ ] **TOOL-05**: MCP client connects to MCP servers and exposes their tools to agents via the tool registry
- [ ] **TOOL-06**: Memory tool (MCP-backed) provides access to session, global, and agent-private memory domains

### Memory

- [ ] **MEM-01**: Session memory is stored and managed by the engine (thread continuity, task state, approvals, artifact refs)
- [ ] **MEM-02**: Global memory is stored and managed by the engine (durable profile, facts, promoted lessons)
- [ ] **MEM-03**: Agent-private memory is isolated per agent process
- [ ] **MEM-04**: Memory access is tool-mediated and permissioned (via MCP memory tool)
- [ ] **MEM-05**: Memory promotion from session to global requires explicit agent proposal + user approval (or autonomous commit when autonomy policy allows)

### Agent Runtime

- [ ] **AGT-01**: Agent config loader reads YAML manifests defining persona, tool permissions, skill permissions, model preferences, autonomy policy, ports, log config
- [ ] **AGT-02**: Agent runtime loop connects to engine on startup, registers, handles incoming events, invokes tools, streams responses
- [ ] **AGT-03**: Default `breqy` agent definition exists (agent.yaml + persona.md) with persona traits: sharp, calm, high-agency, slightly disruptive, trustworthy
- [ ] **AGT-04**: Model provider abstraction defines streaming inference interface (token/chunk streaming + tool-call deltas)
- [ ] **AGT-05**: GitHub Copilot auth provider implements RFC 8628 device authorization grant
- [ ] **AGT-06**: OpenAI Codex auth provider implements OpenAI custom device flow
- [ ] **AGT-07**: Claude/Anthropic auth provider implements PKCE Authorization Code flow (URL displayed, user pastes code back)
- [ ] **AGT-08**: Google Gemini auth provider implements RFC 8628 device authorization grant
- [ ] **AGT-09**: Qwen/DashScope auth provider accepts API key via masked input and stores in keyring
- [ ] **AGT-10**: CredentialStore wraps OS keyring under namespaced keys (`breqy/<provider>`); injected into runners; credentials never written to plain config files
- [ ] **AGT-11**: Skills loader reads skill manifests and instructions from disk; validates required tools against agent permissions before invocation

### Sessions & Control

- [ ] **SES-01**: Sessions persist across engine restart; TUI reconnect resumes same session with full history
- [ ] **SES-02**: Session tracks participants (primary agent + any subagents) with join/leave timestamps
- [ ] **SES-03**: Stop control cancels active agent work as soon as possible
- [ ] **SES-04**: Stop-and-steer control lets current atomic step finish, stops the active plan, accepts new direction
- [ ] **SES-05**: Steer control lets in-flight step complete, updates context and plan, continues without stopping overall task
- [ ] **SES-06**: Circuit-break control hard-kills all related agent processes immediately and records emergency termination in session state
- [ ] **SES-07**: Engine owns canonical task state; agents propose and update tasks; user steering can modify plan mid-flight
- [ ] **SES-08**: Sessions can attach to one or more workspace paths; default operational scope is within attached workspaces

### TUI Client

- [ ] **TUI-01**: TUI session list screen lists active sessions and allows creating a new session or resuming an existing one
- [ ] **TUI-02**: TUI chat screen streams incoming message chunks from the engine in real time
- [ ] **TUI-03**: TUI renders all core typed events (message, task, tool invocation, approval, control) from typed contracts — no heuristic payload guessing
- [ ] **TUI-04**: TUI task list widget shows current task and todo state updated live
- [ ] **TUI-05**: TUI inline approval prompt widget surfaces approval requests with approve/deny + "approve for session" options
- [ ] **TUI-06**: TUI control bar provides stop, stop-and-steer, steer, and circuit-break actions
- [ ] **TUI-07**: TUI shows agent participation status (which agents are active in the session)
- [ ] **TUI-08**: TUI tool event widget shows tool name, status, summary, and output during execution
- [ ] **TUI-09**: TUI runner auth panel displays all configured runners with auth status, and drives inline auth flows (device flow with OSC8 URL + code, PKCE with URL + paste input, API key with masked input)
- [ ] **TUI-10**: TUI logs/events view shows structured engine and agent events
- [ ] **TUI-11**: TUI supports slash commands
- [ ] **TUI-12**: TUI provides provider/model registration and a model selection view (reusing mechanism from existing orchestrator)
- [ ] **TUI-13**: For providers like GitHub Copilot that require an agent originator header, the TUI/agent correctly sets the originator identity when making inference calls and on tool use follow-up messages

### Config & Secrets

- [ ] **CFG-01**: Config loader reads YAML manifests and Markdown instruction files for engine and agent configuration
- [ ] **CFG-02**: EngineConfig and AgentConfig dataclasses validate loaded configuration
- [ ] **CFG-03**: SecretProvider ABC abstracts secret retrieval; KeyringProvider implements it using the OS keyring
- [ ] **CFG-04**: Runtime config changes are temporary only (no persistent config mutation from runtime)

## v2 Requirements

### Slice 2 Candidates

- **SL2-01**: SSH tool with whitelist, approve-list, and blacklist host policy
- **SL2-02**: Agent spawning, delegation, and session handoff
- **SL2-03**: Docker and service inspection and basic remediation
- **SL2-04**: Artifact tracking: diffs, logs, reports with DB metadata and file references
- **SL2-05**: Memory retrieval automation and promotion flow enhancements
- **SL2-06**: Background jobs: session-linked and detached, restart survival, progress streaming, cancellation

### Future Channels

- **CH-01**: WebUI channel adapter
- **CH-02**: Telegram channel adapter (production-grade)
- **CH-03**: WhatsApp channel adapter (production-grade)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud-native deployment | Local-first is the core principle for v1 |
| Multi-user accounts and permissions | Personal-first v1; architecture leaves room |
| Rich Web UI | TUI-first; web channel is v2+ |
| Production Telegram/WhatsApp | Future channels |
| MCP integration beyond MCP client | Extension points only for v1 |
| Persistent config editing from UI | File-based config is source of truth in v1 |
| Advanced tracing/metrics stack | structlog + TUI event view sufficient |
| SSH tool | Slice 2 |
| Agent delegation/handoff depth | Slice 2 |
| Docker inspection workflows | Slice 2 |
| Glob/wildcard filesystem policy matching | Exact paths and directory-prefix only in v1 |
| Windows as primary platform | Fast follower; avoid blocking design choices |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOM-01 | Phase 1: Domain Foundation | Pending |
| DOM-02 | Phase 1: Domain Foundation | Pending |
| DOM-03 | Phase 1: Domain Foundation | Pending |
| DOM-04 | Phase 1: Domain Foundation | Pending |
| DOM-05 | Phase 1: Domain Foundation | Pending |
| STR-01 | Phase 2: Storage Layer | Pending |
| STR-02 | Phase 2: Storage Layer | Pending |
| STR-03 | Phase 2: Storage Layer | Pending |
| STR-04 | Phase 2: Storage Layer | Pending |
| STR-05 | Phase 2: Storage Layer | Pending |
| CFG-01 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| CFG-02 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| CFG-03 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| CFG-04 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| A2A-01 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| A2A-02 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| A2A-03 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| A2A-04 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| A2A-05 | Phase 3: Config, Secrets & A2A Protocol | Pending |
| POL-01 | Phase 4: Policy & Approvals | Pending |
| POL-02 | Phase 4: Policy & Approvals | Pending |
| POL-03 | Phase 4: Policy & Approvals | Pending |
| POL-04 | Phase 4: Policy & Approvals | Pending |
| POL-05 | Phase 4: Policy & Approvals | Pending |
| POL-06 | Phase 4: Policy & Approvals | Pending |
| ENG-01 | Phase 5: Engine Runtime | Pending |
| ENG-02 | Phase 5: Engine Runtime | Pending |
| ENG-03 | Phase 5: Engine Runtime | Pending |
| ENG-04 | Phase 5: Engine Runtime | Pending |
| ENG-05 | Phase 5: Engine Runtime | Pending |
| ENG-06 | Phase 5: Engine Runtime | Pending |
| TOOL-01 | Phase 6: Tools | Pending |
| TOOL-02 | Phase 6: Tools | Pending |
| TOOL-03 | Phase 6: Tools | Pending |
| TOOL-04 | Phase 6: Tools | Pending |
| TOOL-05 | Phase 6: Tools | Pending |
| TOOL-06 | Phase 6: Tools | Pending |
| MEM-01 | Phase 7: Memory | Pending |
| MEM-02 | Phase 7: Memory | Pending |
| MEM-03 | Phase 7: Memory | Pending |
| MEM-04 | Phase 7: Memory | Pending |
| MEM-05 | Phase 7: Memory | Pending |
| AGT-01 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-02 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-03 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-04 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-05 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-06 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-07 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-08 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-09 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-10 | Phase 8: Agent Runtime & Auth | Pending |
| AGT-11 | Phase 8: Agent Runtime & Auth | Pending |
| SES-01 | Phase 9: Sessions & Control | Pending |
| SES-02 | Phase 9: Sessions & Control | Pending |
| SES-03 | Phase 9: Sessions & Control | Pending |
| SES-04 | Phase 9: Sessions & Control | Pending |
| SES-05 | Phase 9: Sessions & Control | Pending |
| SES-06 | Phase 9: Sessions & Control | Pending |
| SES-07 | Phase 9: Sessions & Control | Pending |
| SES-08 | Phase 9: Sessions & Control | Pending |
| TUI-01 | Phase 10: TUI Client | Pending |
| TUI-02 | Phase 10: TUI Client | Pending |
| TUI-03 | Phase 10: TUI Client | Pending |
| TUI-04 | Phase 10: TUI Client | Pending |
| TUI-05 | Phase 10: TUI Client | Pending |
| TUI-06 | Phase 10: TUI Client | Pending |
| TUI-07 | Phase 10: TUI Client | Pending |
| TUI-08 | Phase 10: TUI Client | Pending |
| TUI-09 | Phase 10: TUI Client | Pending |
| TUI-10 | Phase 10: TUI Client | Pending |
| TUI-11 | Phase 10: TUI Client | Pending |
| TUI-12 | Phase 10: TUI Client | Pending |
| TUI-13 | Phase 10: TUI Client | Pending |

**Coverage:**
- v1 requirements: 57 total
- Mapped to phases: 57 ✓
- Unmapped: 0 ✓

---

## v1.1 Requirements — Provider/Model Runtime Switching

### Model Display & Discovery

- [ ] **MDL-01**: TUI displays current provider and model in `AgentStatusBar` immediately after agent connects
- [ ] **MDL-02**: Agent sends `ModelInfoEvent` to engine/TUI on connect and after every provider switch
- [ ] **MDL-03**: `ModelProvider` base class provides `list_models()` method returning `(model_id, display_name)` pairs, with default returning the configured model
- [ ] **MDL-04**: `CopilotProvider` overrides `list_models()` to query the `/models` API endpoint dynamically
- [ ] **MDL-05**: Hardcoded fallback model lists exist for all 5 providers for use when dynamic discovery is unavailable

### Model Switching

- [ ] **MSW-01**: User can open model selector via `ctrl+m`, which sends `ModelListRequestedEvent` to agent and populates `ModelSelectScreen` with response
- [ ] **MSW-02**: User can select a provider/model in `ModelSelectScreen`, which sends `ModelSwitchRequestedEvent` to agent
- [ ] **MSW-03**: Agent rebuilds provider on switch request; new model continues same chat session (ephemeral — `agent.yaml` not mutated)
- [ ] **MSW-04**: Same-model guard: selecting the already-active model skips rebuild and sends confirming `ModelInfoEvent`
- [ ] **MSW-05**: Switch failure preserves old provider; error sent as system message; `ModelInfoEvent` with old model re-sent

### A2A Events & Routing

- [ ] **MAE-01**: Four new event types: `model.info`, `model.list.requested`, `model.list.response`, `model.switch.requested`
- [ ] **MAE-02**: `ModelListRequestedEvent` and `ModelSwitchRequestedEvent` routed by engine to session's primary agent (targeted send)
- [ ] **MAE-03**: `ModelInfoEvent` and `ModelListResponseEvent` broadcast by engine to all session clients

### Auth & Integration

- [ ] **MAI-01**: `CredentialStore` extracted from `_build_provider()` to `main()` and injected into both provider builder and `AgentRuntime`
- [ ] **MAI-02**: Unauthenticated provider triggers auth on demand via existing notice event pattern when first `stream()` is called after switch
- [ ] **MAI-03**: TUI clears model info on `AGENT_DISCONNECTED`; `_model_list_pending` debounce flag prevents duplicate `ctrl+m` requests

### v1.1 Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MDL-01 | Phase 5: TUI Wiring | Pending |
| MDL-02 | Phase 3: Agent Runtime | Pending |
| MDL-03 | Phase 2: Provider list_models() | Pending |
| MDL-04 | Phase 2: Provider list_models() | Pending |
| MDL-05 | Phase 2: Provider list_models() | Pending |
| MSW-01 | Phase 5: TUI Wiring | Pending |
| MSW-02 | Phase 5: TUI Wiring | Pending |
| MSW-03 | Phase 3: Agent Runtime | Pending |
| MSW-04 | Phase 3: Agent Runtime | Pending |
| MSW-05 | Phase 3: Agent Runtime | Pending |
| MAE-01 | Phase 1: Domain Events & Models | Pending |
| MAE-02 | Phase 4: Engine Routing | Pending |
| MAE-03 | Phase 4: Engine Routing | Pending |
| MAI-01 | Phase 3: Agent Runtime | Pending |
| MAI-02 | Phase 3: Agent Runtime | Pending |
| MAI-03 | Phase 5: TUI Wiring | Pending |

**v1.1 Coverage:**
- v1.1 requirements: 16 total
- Mapped to phases: 16 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-22*
*Last updated: 2026-03-29 — added v1.1 Provider/Model Runtime Switching requirements*

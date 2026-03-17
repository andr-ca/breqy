# Breqy Architecture

## 1. Architecture goals
The architecture must:
- support a long-running local-first runtime
- cleanly separate engine, agents, and channels
- preserve sessions and operational state durably
- support multi-agent participation with strong isolation
- stay modular and loosely coupled via interfaces and DI
- enable safe tool execution and approval policies
- remain extensible for future channels, providers, and storage backends

## 2. Runtime topology

### Core components
1. **breqy-engine**
   - process supervisor and orchestrator
   - session store owner
   - event bus owner
   - authentication boundary
   - channel ingress point
   - shared memory owner
   - scheduler and background job coordinator

2. **breqy agent processes**
   - separate processes
   - connect and register to engine over A2A
   - execute tools
   - maintain agent-private memory
   - participate in sessions
   - may spawn or be spawned as subagents

3. **Channel apps**
   - TUI first
   - future WebUI, Telegram, and WhatsApp adapters
   - connect only to engine
   - stream session events and user messages

## 3. Responsibility split

### Engine responsibilities
- session storage
- channel connections
- routing messages to agents
- spawning agent and subagent processes
- global and session memory storage and indexing
- scheduling and background jobs
- task state ownership
- authentication
- event persistence
- observability aggregation at engine level
- policy enforcement and approval orchestration

### Agent responsibilities
- reasoning and planning within granted constraints
- tool execution
- agent-private memory
- local logging and observability
- proposing task updates
- proposing memory writes and promotions
- participating in delegation and handoff

### Shared and dual responsibilities
- approval workflow may exist at both engine and agent layers
- observability exists at both process level and runtime level

## 4. Communication model

### Protocol
- standard A2A between engine and agents
- event-driven and streaming first
- request and response also supported
- Slice 1 must define a canonical typed contract for core runtime messages and events
- shared schema models must be used by engine, agents, and channels so incompatible payload variants do not emerge

### Network model
- engine has a configured port
- each agent has a configured port
- agent starts and attempts connection to engine
- channel connects only to engine
- engine binds to localhost by default, configurable otherwise

### Minimal A2A runtime profile
For v1, Breqy must define a minimal runtime profile for A2A that is strict enough for shared implementation across the engine, agents, and TUI-facing event translation layer. The transport may evolve, but the message contract must not be informal. At minimum, the profile must define envelope fields such as message or event type, schema version, event ID, correlation ID, session ID, agent ID, timestamps, and payload. Core event types such as tool invocation, approval, task update, control, and message events must have required fields defined in shared schema models.

### Suggested communication semantics
Core event families:
- session events
- message events
- task events
- tool events
- approval events
- memory events
- agent lifecycle events
- artifact events
- control events
- background job events

## 5. Domain model

### Primary domain objects
- **Session**
- **Participant**
- **Agent**
- **Message**
- **Event**
- **Task**
- **ApprovalRequest**
- **ApprovalDecision**
- **Artifact**
- **Workspace**
- **MemoryRecord**
- **Job**
- **Skill**
- **ToolInvocation**
- **PolicyRule**

### Key relationships
- session has many participants, messages, tasks, events, artifacts, jobs
- primary agent belongs to session
- subagents join session as participants
- agent has config, local memory, tool and skill permissions
- engine owns global and session stores
- artifacts belong to session and may reference workspace files
- jobs may belong to session or be detached with backlink
- approvals link to actions and tool invocations
- policy rules apply at global, agent, and session scope

## 6. Persistence architecture

### Storage approach
Hybrid by design:
- DB canonical state
- file-based summaries, logs, and artifacts
- vector and index stores abstracted behind interfaces

To reduce SQLite write contention in v1, the engine should use a centralized event writer that accepts queued events from agents and writes them sequentially to the canonical store. Agents should remain non-blocking and should not compete directly for DB writes.

### Canonical DB contents
- sessions
- participants
- messages
- tasks
- approvals
- tool invocations
- jobs
- artifact metadata
- memory metadata
- event log

### File-based contents
- markdown summaries
- agent logs
- session transcript exports
- generated files
- patches and diffs
- command outputs
- job logs
- debug snapshots

Every approval request, approval decision, and tool invocation must be written to the session event log before execution begins, or atomically at execution start, so the audit trail remains durable even when work fails mid-step.

### Storage abstraction
All persistence must be behind interfaces and injected through dependency injection.

Initial likely backend:
- SQLite

Future backend possibilities:
- Postgres
- alternative vector stores
- alternative artifact metadata stores

## 7. Memory architecture

### Global memory
Owned by engine.
Use for:
- durable profile and facts
- long-lived environment, user, and system knowledge
- promoted lessons and summaries

### Session memory
Owned by engine.
Use for:
- thread continuity
- working memory
- session summaries
- task state
- approvals
- artifact references
- episodic session history

### Agent-private memory
Owned by each agent.
Use for:
- agent-specific preferences and heuristics
- private notes
- local retrieval memory
- reflection history

### Storage forms
Use multiple forms:
- structured records
- markdown and text summaries
- vector retrieval index
- append-only event history

Recommended pattern:
**event log -> summaries and checkpoints -> structured facts + retrieval index**

## 8. Permission and policy architecture

### Policy scopes
- global
- agent
- session

Rule resolution:
- most restrictive wins

### Policy types
- tool allow and deny
- skill allow and deny
- autonomy level
- filesystem path rules
- SSH host rules
- memory access rules
- approval requirements

### Approval behavior
- inline UX surfaced by channel
- engine-enforced canonical approval state
- session-scoped temporary grants supported

## 9. Agent architecture

### Agent filesystem structure (recommended)
```text
agents/
  breqy/
    agent.yaml
    persona.md
    memory.yaml
    startup/
    logs/
```

### Minimum agent manifest contents
- id and name
- display name
- port
- model preferences
- persona file
- tool permissions
- skill permissions
- memory config
- autonomy policy
- subagent spawning policy
- startup hooks
- log level
- log path

### Dynamic agents
Support:
- ephemeral runtime agents generated from templates and base definitions
- optional promotion into persistent saved agents

## 10. Skill architecture

### Runtime rule
Skills shape how work is carried out, but tools remain the only executable permission boundary. The `PolicyEvaluator` must validate tool access independently of any skill metadata. A skill may require or suggest tools, but it must never grant effective permission to use them.

### Recommended skill structure
```text
skills/
  debug-docker/
    skill.yaml
    instructions.md
    scripts/
    refs/
```

### Runtime behavior
When invoking a skill:
- load the skill manifest and instructions
- inject the skill into the agent runtime as structured context rather than as an implicit permission source
- expose supporting assets and references
- validate required tools, policy, and environment compatibility before execution
- provide expected outputs and success criteria
- allow the agent to use the skill as structured guidance

In v1, a skill may be injected as explicit task context and instruction material associated with the current task or plan. Retrieval or summarization strategies may evolve later, but the invocation path must remain explicit and inspectable.

Skills do not grant permission.

## 11. Workspace architecture
Sessions may attach to one or more workspaces.

Default operational boundary:
- attached workspaces only

Expanded scope:
- only by explicit policy

Future extension:
- first-class Project object above sessions

## 12. Secrets architecture
Secrets must be abstracted behind a secret-provider interface.

v1 approach:
- secure local secret abstraction, separate from normal config files
- swappable later
- keyring-backed storage preferred on supported Linux environments
- fallback implementations, if any, must remain outside ordinary YAML or Markdown config and be clearly treated as lower-trust

Use cases:
- provider auth
- channel tokens
- SSH-related secret handling
- future external tool credentials

## 12a. Runner authentication architecture

### Overview
All five orchestrator runners authenticate via an `AuthProvider` ABC. Each provider implementation encapsulates the full auth flow for that vendor. A shared `CredentialStore` wraps the OS keyring under a namespaced key per provider (`breqy/<provider>`).

### `AuthProvider` ABC
```
AuthProvider
  authenticate() -> None          # trigger the auth flow interactively
  is_authenticated() -> bool      # check keyring for a valid token
  get_token() -> str | None       # retrieve stored token (or None)
  revoke() -> None                # delete token from keyring
```

### Concrete implementations

| Provider | Auth flow | Endpoints |
|---|---|---|
| `GitHubCopilotAuth` | RFC 8628 device flow | `POST https://github.com/login/device/code` → poll `https://github.com/login/oauth/access_token` |
| `CodexAuth` | OpenAI custom device flow | `POST https://auth.openai.com/api/accounts/deviceauth/usercode` → poll `/deviceauth/token` → PKCE exchange `/oauth/token` |
| `ClaudeAuth` | PKCE Authorization Code | `https://claude.ai/oauth/authorize` (URL displayed, user pastes code back) → token at `https://platform.claude.com/v1/oauth/token` |
| `GeminiAuth` | RFC 8628 device flow | `POST https://oauth2.googleapis.com/device/code` → poll `https://oauth2.googleapis.com/token` |
| `QwenAuth` | API key (no OAuth) | User pastes key into TUI masked input; stored directly in keyring |

### `CredentialStore`
Thin wrapper around the `keyring` library:
- `get(provider: str) -> str | None`
- `set(provider: str, token: str) -> None`
- `delete(provider: str) -> None`
- Namespace: `breqy/<provider>` (e.g., `breqy/copilot`, `breqy/codex`)

Injected into runners at construction time. Runners call `store.get(provider)` at run time and inject the token into the subprocess env dict — no change to subprocess invocation interface.

### Auth TUI panel
The `AuthPanel` Textual widget drives the interactive auth flow:
- Renders a status table: one row per runner, showing authenticated / unauthenticated
- On user action (select runner, press Enter): calls `provider.authenticate()`
- **Device flow providers**: display `verification_uri` as OSC8 clickable hyperlink + `user_code`; spawn background polling coroutine; update row when polling completes
- **PKCE (Claude)**: display authorization URL as OSC8 hyperlink; render `Input` widget for auth code paste; on submit call token exchange
- **API key (Qwen)**: render masked `Input` widget; on submit call `store.set()`
- `AuthPanel` is composed into `OrchestratorApp` and reachable via the `A` keybind
- `breqy-orchestrator auth [provider]` CLI subcommand opens `AuthApp` (a minimal standalone Textual app wrapping only `AuthPanel`) without starting the orchestrator loop

### Integration with runners
Each runner receives a `CredentialStore` via constructor injection. The runner calls `store.get(self._provider)` before spawning the subprocess and merges the token into `extra_env`. Runners do not read from `.env` directly — the credential store is the sole source of truth for provider tokens at runtime.

## 13. Observability architecture
v1 includes:
- structured logs
- human-readable logs
- TUI activity and event view

Engine logs:
- lifecycle
- routing
- auth
- orchestration
- persistence
- scheduler

Agent logs:
- tool execution
- reasoning checkpoints if configured
- memory operations
- failures and restarts

## 14. Suggested package and module layout
High-level Python monorepo with clear package boundaries:

```text
repo/
  apps/
    breqy-engine/
    breqy-tui/
  packages/
    core-domain/
    engine-runtime/
    agent-runtime/
    a2a-adapter/
    session-store/
    event-store/
    memory-core/
    artifact-core/
    policy-engine/
    approval-core/
    task-core/
    tool-core/
    skill-core/
    provider-core/
    auth-core/
    secret-core/
    workspace-core/
    observability-core/
    channel-sdk/
  agents/
    breqy/
  skills/
  config/
  docs/
```

## 15. Key interfaces to define early
Recommended core abstractions:
- `SessionRepository`
- `EventRepository`
- `TaskRepository`
- `ArtifactRepository`
- `MemoryRepository`
- `VectorIndex`
- `SecretProvider`
- `ModelProvider`
- `ToolExecutor`
- `SkillLoader`
- `PolicyEvaluator`
- `ApprovalService`
- `AgentRegistry`
- `AgentSpawner`
- `ChannelAdapter`
- `WorkspaceResolver`
- `AuthProvider` — per-provider OAuth/key auth flow (device flow, PKCE, or key entry)
- `CredentialStore` — keyring-backed token storage, injected into runners

## 16. Implementation guidance
### Start with Slice 1
Do not overbuild before proving:
- engine lifecycle
- TUI connection
- persistent sessions
- streaming events
- task list
- tool execution
- approvals
- interruption controls
- typed event contracts

### Then add Slice 2
- shared memory
- SSH
- delegation
- handoff
- Docker inspection and remediation
- artifacts

## 17. v1 implementation risks to watch
- Agent process sprawl: enforce session-level and runtime-level limits early.
- TUI responsiveness: input and rendering must remain responsive during streaming and tool activity.
- SQLite write contention: use WAL mode and a centralized event writer from the start.

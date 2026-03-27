# Phase 8 Agent Runtime & Auth Design

## Goal

Deliver a fully operational default `breqy` agent runtime that loads from disk, registers with the engine, processes session work through the typed A2A contract, invokes tools through the existing mediated tool path, supports all five real provider integrations, and stores credentials only in the OS keyring behind Breqy-native abstractions.

## Scope

Phase 8 covers:
- the default `breqy` agent definition directory with validated `agent.yaml` and `persona.md`
- a real agent runtime in `breqy/agents/` that connects to the engine and runs an inference loop
- engine-side agent registration and message routing needed for agent round trips
- a Breqy-owned `ModelProvider` abstraction with streaming and tool-call signaling
- all five provider integrations for auth and execution: GitHub Copilot, Codex, Claude, Gemini, and Qwen
- a Breqy-owned `CredentialStore` layered over `SecretProvider`
- skill loading and validation against agent tool permissions
- private-memory runtime wiring for the owning agent only

Phase 8 explicitly does not cover:
- TUI auth panel implementation beyond whatever backend contracts Phase 10 will consume
- session control primitives and canonical task-state ownership beyond what is needed for the runtime loop
- cloud or multi-user authentication models
- replacing the existing CLI-backed provider execution model with in-process SDK clients unless already required by a provider adapter

## Architecture

### Core design choice

Phase 8 should reuse the already-tested provider integrations under `system/orchestrator/`, but only through a Breqy-owned anti-corruption layer. Breqy must not directly depend on orchestrator-specific credential storage or runner contracts as its public architecture. Instead, Phase 8 should adapt the proven auth and runner behavior into interfaces that match the repo's declared design: `ModelProvider`, `CredentialStore`, agent runtime services, and `SecretProvider`-backed dependency injection.

This gives Phase 8 the speed and practical coverage of the working orchestrator integrations while preserving Breqy's architectural boundaries.

### Core components

- `AgentConfigLoader`
  - extends config loading so an agent directory resolves both `agent.yaml` and `persona.md`
  - returns a validated runtime-ready configuration object
- `AgentRuntime`
  - long-lived agent process entrypoint
  - owns engine connection, message handling, provider invocation, tool execution coordination, and response streaming
- `ModelProvider`
  - Breqy-native inference abstraction
  - streams assistant output chunks and emits structured tool-call deltas
- provider adapters
  - one adapter per real provider
  - wrap or reuse the proven auth/runner logic from `system/orchestrator/`
  - expose a consistent Breqy-native interface
- `CredentialStore`
  - Breqy-owned wrapper over `SecretProvider`
  - stores provider credentials under provider-specific namespaced keys
- `SkillLoader`
  - loads skill metadata and instructions from disk
  - validates required tools against agent permissions before a skill is made available to runtime execution
- engine registration/router updates
  - bind connected agent runtime clients to `agent_id`
  - route session work to the primary agent
- private-memory adapter
  - completes Phase 7's deferred private-memory runtime boundary by providing an agent-owned store accessible only through trusted runtime context

## Runtime flow

### Agent startup

On startup, the agent runtime should:
1. load and validate `agent.yaml`
2. load `persona.md`
3. construct `CredentialStore`, provider registry, skill loader, and private-memory store through DI
4. connect to the engine via `A2AClient`
5. send an explicit registration/lifecycle event containing the agent identity
6. begin listening for session-directed work

The runtime entrypoint should match the already-wired spawn target in `breqy/engine/agent_spawner.py`, so Phase 8 fills in `breqy.agents.runtime` rather than changing the spawner contract.

### Message handling loop

When the engine routes user work to the agent runtime:
- the runtime resolves the active persona and skill context
- it requests a streaming generation from the selected `ModelProvider`
- text chunks are emitted as `MessageChunkEvent`
- a final assistant message is emitted as the existing typed message event path expects
- provider tool-call deltas are translated into calls through the existing `ToolService` path, not ad hoc subprocess logic

Tool usage must remain engine-mediated. The agent runtime may decide to call a tool, but actual execution still flows through the same policy, approval, persistence, and eventing path already implemented in `breqy/tools/service.py`.

### Engine-mediated tool round trip

Because the agent runtime is a separate process, Phase 8 must define an explicit cross-process tool contract rather than implying in-process `ToolService` access. The required round trip is:
1. provider emits a normalized tool-call delta
2. agent runtime sends a typed tool-execution request event over A2A containing at minimum `session_id`, `agent_id`, `tool_name`, normalized arguments, and a correlation/invocation identifier
3. engine receives that request, invokes `ToolService`, persists and emits the usual invocation lifecycle events, and keeps approval/policy logic fully engine-owned
4. engine returns a typed tool-result event over A2A containing the same correlation/invocation identifier plus structured success or failure payload
5. agent runtime appends that structured tool result into the provider conversation state and resumes the normalized provider turn loop

The engine remains the sole owner of invocation persistence and approval state. The agent runtime remains a requester and consumer of structured results only.

Private-memory operations are the one mediated special case. For `memory` tool calls targeting `private` scope, the contract should be:
1. agent runtime sends the normal typed tool-execution request to the engine
2. engine performs the normal policy, approval, and invocation-persistence checks
3. engine sends a typed delegated private-memory operation request back to the same agent runtime with validated operation data and the invocation identifier
4. agent runtime executes the operation against its local agent-owned private-memory store
5. agent runtime returns a typed delegated private-memory result to the engine
6. engine finalizes the canonical invocation lifecycle and returns the normal `ToolExecutionResultEvent`

This preserves engine mediation while keeping the private-memory store agent-owned.

Phase 8 should introduce explicit typed event models for this request/response edge rather than overloading the existing post-execution lifecycle events. The existing tool lifecycle events remain the audit and broadcast path after execution begins, while the new request/result events exist specifically for agent-to-engine invocation handoff and engine-to-agent tool-result delivery.

These request/result events should be treated as A2A transport events first, not additional durable audit-log records by default. Durable audit history remains anchored in the existing tool invocation lifecycle events emitted by the engine once `ToolService` accepts execution. This avoids duplicating persistence responsibilities while still giving the agent/runtime a typed request-response contract.

### Skill activation semantics

Phase 8 should treat skills as explicit runtime context, not as ambient startup behavior. The activation rules should be:
- `AgentConfig.skill_permissions` defines the allowed skill set the agent may activate
- `AgentConfig.skill_permissions` remains a list field in `agent.yaml`
- wildcard permission should be represented as `"skill_permissions": ["*"]` in the normalized config shape, matching the current PRD direction without changing the field type
- `SkillLoader` may discover and validate only skills inside that allowlist
- a skill becomes active per request or task turn when the engine dispatch contract explicitly provides `active_skill_ids` for the current unit of work
- inactive skills are not injected into every provider turn by default
- skill activation remains session/task context, not a persistent permission change

This keeps `skill_permissions` meaningful, prevents silent prompt bloat, and preserves the documented rule that skills shape behavior but do not grant tool authority.

The source of truth for turn-time skill selection should be the engine-to-agent work-dispatch payload. Phase 8 should include `active_skill_ids: list[str]` in that typed dispatch model so the runtime receives an explicit list of skills to activate for the current turn.

Invalid skill handling should be strict and deterministic:
- the engine should sanitize requested skill ids before dispatch
- the runtime should still validate every received `active_skill_id`
- if any received skill id is unknown or disallowed for that agent, the runtime should reject the turn with a structured error event rather than silently dropping it

### Normalized provider turn contract

Phase 8 should use one normalized turn loop across all providers:
1. runtime builds the provider input from persona, current request, session context bundle, and any explicitly active skills
2. provider streams zero or more text chunks and zero or more structured tool-call deltas
3. when a tool call is emitted, the runtime pauses provider progression for that tool action, routes the call through the existing mediated tool path, and captures the structured result
4. the tool result is appended to the provider conversation state in a provider-neutral internal format
5. the runtime resumes the same provider turn until it reaches either another tool call or final assistant completion
6. the turn ends only when the provider emits a final assistant completion without a pending tool call

Multi-step tool loops are required in Phase 8 for providers whose reused integration path can emit structured tool calls. Phase 8 acceptance does not require every provider adapter to support tool calling on day one. The minimum requirement is:
- the runtime-wide normalized tool loop exists and is fully tested
- at least one real provider path proves end-to-end tool-calling through that loop
- providers without practical tool-call support in their reused integration may operate as chat-only adapters in Phase 8 while still supporting auth and streaming/text completion behavior

This keeps the runtime contract consistent without inventing fake tool semantics for providers whose current working integration path does not expose them.

### Engine routing updates

`EngineServer` should be extended from generic broadcast-only behavior to explicit agent-aware routing:
- registration/lifecycle events associate `agent_id` with the connected `client_id`
- disconnect handling removes stale registry entries
- incoming user messages for a session are routed to that session's primary agent
- agent-originated chunks/results are broadcast back to subscribed clients after registry and session checks

This should preserve the current event bus and A2A envelope behavior rather than inventing a second transport path.

The concrete typed dispatch trigger for runtime execution should be a new engine-to-agent event model, provisionally named `AgentWorkRequestedEvent`. It should carry at minimum:
- `session_id`
- `agent_id`
- triggering `message_id`
- current user message content
- optional task context reference
- `active_skill_ids`
- correlation id for the resulting streamed response

Phase 8 should treat `AgentWorkRequestedEvent` as the single source of truth for starting agent work, rather than asking the runtime to infer dispatch intent from broadcast chat events.

`AgentWorkRequestedEvent` should carry an embedded session context bundle. Phase 8 should not leave prior conversation context implicit and should not add a second fetch path for this phase. The dispatch contract should therefore include:
- recent canonical message history needed for the turn
- relevant memory summary or checkpoint data
- any task context included for the current turn

Planning should assume the engine is responsible for assembling this authoritative session context bundle before dispatch.

## Provider architecture

### `ModelProvider` contract

Phase 8 should define a Breqy-native model execution interface that supports real streaming and tool-call signaling. At minimum the contract should support:
- streaming assistant text chunks
- structured tool-call delta emission
- final completion metadata
- provider/model identification

The interface should be owned by Breqy and remain independent from the orchestrator's runner contracts, even if adapters internally reuse them.

### Provider adapters

All five providers should be supported in Phase 8:
- GitHub Copilot
- Codex
- Claude
- Gemini
- Qwen

The recommended implementation is adapter-based reuse:
- preserve orchestrator-tested auth logic patterns and CLI integration behavior where practical
- map each provider's auth and execution semantics into Breqy-native types
- inject credentials through `CredentialStore` at runtime rather than letting providers read files or global environment directly

### Why adapters instead of direct imports

Directly treating `system/orchestrator/` as the runtime API would leak the wrong boundaries into Breqy:
- duplicate credential storage logic
- provider execution contracts not shaped around Breqy events and runtime state
- weaker alignment with `SecretProvider` and DI requirements

Adapters let Breqy own the public architecture while still benefiting from proven implementation logic.

### Provider and model selection source of truth

For Phase 8, provider and default model selection should be agent-config driven, not session-driven. `agent.yaml` should be the source of truth for:
- the selected provider id
- the default model id for that provider
- any provider-specific execution settings that must be known at runtime startup

The manifest contract should be explicit in this phase. `agent.yaml` should add these fields:
- `provider: str`
  - required
  - one of `copilot`, `codex`, `claude`, `gemini`, `qwen`
- `model: str`
  - required
  - provider-specific default model identifier for runtime use
- `provider_settings: dict[str, str]`
  - optional
  - provider-specific non-secret execution settings needed at startup

The runtime may keep this selection in memory during execution, but Phase 8 should not add session-level provider switching yet. That belongs to the later TUI/model-selection work. Tests and config loading for Phase 8 should therefore assume one configured provider/model pair per running agent process.

## Authentication architecture

### `CredentialStore`

Phase 8 should add a Breqy-owned `CredentialStore` that wraps `SecretProvider` rather than calling keyring directly from runtime code. The storage namespace should preserve provider separation, using stable provider-specific identifiers beneath the Breqy service namespace.

Required behavior:
- `get(provider: str) -> ProviderCredential | None`
- `set(provider: str, credential: ProviderCredential) -> None`
- `delete(provider: str) -> None`
- no plain-file persistence
- no `.env` storage for provider credentials

`ProviderCredential` should be a typed Breqy model that can store structured credential payloads, not only a single token string. At minimum it should support:
- provider id
- credential kind
- access token or API key
- refresh token when applicable
- expiry metadata when applicable
- optional extra provider metadata needed for later token exchange or refresh

The secret backend may persist this typed payload as serialized structured data, but the runtime API should remain typed.

This avoids duplicating secret logic already present in `breqy/secrets/provider.py` and keeps provider credentials behind the same abstraction family as the rest of the system.

### Supported auth flows

Phase 8 should support the following real flows:
- GitHub Copilot: device flow
- Codex/OpenAI: device flow with token exchange
- Claude: PKCE/browser URL plus pasted code exchange
- Gemini: API key entry, matching the already-working integration pattern found in the repository today
- Qwen: masked API key entry

Important design note: repository docs currently describe Gemini as device-flow based in `docs/architecture.md`, but the existing working integration in `system/orchestrator/` uses API-key auth. Phase 8 explicitly chooses API-key auth for Gemini and should update the docs accordingly.

### Breqy-native auth service contract

Phase 8 should expose a backend auth interface that later TUI work can consume without knowing provider internals. At minimum, the contract should support:
- `start(provider: str) -> AuthSession`
  - begins an interactive auth flow
  - returns current state plus any immediate payload such as verification URL, user code, or whether an API key/code submission is required
- `get_status(provider: str) -> AuthStatus`
  - reports whether the provider is authenticated, unauthenticated, in-progress, or failed
- `submit_code(provider: str, code: str) -> AuthStatus`
  - used for PKCE/code-paste flows such as Claude
- `submit_secret(provider: str, secret: str) -> AuthStatus`
  - used for masked API-key entry flows such as Qwen and the currently implemented Gemini path
- `revoke(provider: str) -> None`
  - deletes stored credentials

`AuthSession` / `AuthStatus` should be typed Breqy models that capture, when relevant:
- provider id
- flow kind (`device`, `pkce_code`, `api_key`)
- verification URL
- user code
- display message
- current status
- last error

This lets Phase 8 define the backend contract now while leaving Phase 10 free to build the specific TUI panels against stable typed state.

## Skill loading

### Loader behavior

Skills should remain structured instruction assets, not implicit permissions. Phase 8 should add a loader that:
- reads skill metadata and instructions from disk
- validates file presence and manifest shape
- extracts required tool names
- rejects skills whose required tools are not permitted by `AgentConfig.tool_permissions`
- returns structured skill context that the runtime can inject into model prompts or task context

Phase 8 should assume and enforce a minimal explicit skill manifest shape so planning does not need to rediscover it:
- `skill.yaml` in the skill directory
- required fields: `id`, `description`, `instructions_file`
- optional field: `required_tools`
- instructions loaded from the referenced Markdown file

`required_tools` should be the field matched against `AgentConfig.tool_permissions`.

The canonical skill discovery root remains the repository top-level `skills/` directory, matching the documented architecture. Phase 8 should create that top-level directory and support `system/skills/` only as a temporary compatibility source during transition.

### Permission model

The loader must enforce compatibility but must not grant permissions. Tool authority continues to live in policy and tool execution services. This preserves the rule already documented in `docs/architecture.md`.

## Private memory wiring

Phase 7 intentionally deferred private-memory runtime integration. Phase 8 should complete that boundary as follows:
- each running agent gets an agent-owned private-memory store instance
- private-memory tool requests are allowed only when trusted execution context matches the owning `agent_id`
- the engine does not treat private memory as canonical session/global memory
- default runtime behavior remains tool-mediated, with the runtime providing the concrete private-memory implementation behind the Phase 7 contract

This closes the gap noted in Phase 7 without collapsing private memory into the engine-owned memory repository.

## Files and responsibilities

Expected new or expanded areas:
- `breqy/agents/runtime.py`
  - runtime entrypoint and event loop
- `breqy/agents/providers/` or similarly focused provider package
  - `ModelProvider` contract and concrete provider adapters
- `breqy/agents/auth/` or similarly focused auth package
  - Breqy-native auth interfaces and provider auth adapters
- `breqy/agents/skills.py` or `breqy/skills/loader.py`
  - skill loading and validation
- `breqy/agents/private_memory.py`
  - runtime-owned private-memory composition
- `agents/breqy/agent.yaml`
  - default agent definition
- `agents/breqy/persona.md`
  - default persona
- `breqy/config/loader.py` and `breqy/config/models.py`
  - richer agent config loading and persona resolution
- `breqy/engine/server.py`
  - registration and routing behavior

The exact package split may vary, but responsibilities should stay narrow and DI-friendly.

## Event and protocol behavior

Phase 8 should continue using the existing typed event vocabulary wherever possible. The runtime should:
- emit `AgentLifecycleEvent` on connect/disconnect or explicit registration/unregistration moments
- emit `MessageChunkEvent` while provider output streams
- emit final message events when a response completes
- cause `ToolInvocationStartedEvent` / completion / failure events through the existing `ToolService` path when provider output requests tools

If the existing event set is missing a small piece of registration semantics, the design may extend it conservatively, but Phase 8 should prefer composing around the existing schema set rather than inventing parallel message types.

For the new agent-to-engine tool handoff, Phase 8 should add explicit typed request/result event models with provisional names:
- `ToolExecutionRequestedEvent`
- `ToolExecutionResultEvent`

These events should carry the correlation and invocation identifiers needed to connect provider tool deltas, engine execution, and runtime continuation.

## Testing strategy

### Unit coverage

- agent config loading, including missing persona failures
- default `breqy` agent definition validation
- credential store behavior over `SecretProvider`
- provider auth adapters for all five providers
- provider execution adapters for all five providers
- runtime translation of provider stream chunks into typed events
- runtime translation of provider tool-call deltas into tool invocations
- skill loader validation against tool permissions
- private-memory ownership enforcement
- engine registration and routing logic

Business-logic files introduced in Phase 8 should meet the repository's 100% coverage requirement.

### Integration coverage

- spawned agent runtime registers with the engine and is visible in the registry
- a user message is routed to the primary agent and yields a streamed response
- a provider-triggered tool call traverses the existing mediated tool path and returns to the runtime
- credentials stored through the auth path are later consumed by the provider adapter without file or env fallback
- private-memory operations succeed for the owning agent and are rejected for other agents

Where possible, integration tests should use deterministic provider doubles around the same Breqy-native interfaces, while provider-specific auth and execution behavior can continue to leverage the existing tested adapter patterns inherited from the orchestrator work.

## Risks and constraints

### Architectural drift risk

The biggest risk is letting `system/orchestrator/` become the de facto public runtime API. Phase 8 must keep Breqy-owned interfaces primary, with orchestrator reuse hidden behind adapters.

### Documentation drift risk

The repo currently contains stale auth documentation, especially around Gemini flow details. Phase 8 should update `docs/architecture.md` and `docs/prd.md` to match the implemented provider behavior chosen in code.

### External dependency risk

Provider integrations depend on external CLIs and remote auth behavior. Tests should avoid requiring live provider accounts, but the design should still preserve the real provider paths as first-class runtime components.

## Deferred work

- TUI auth UX and auth panel rendering details in Phase 10
- provider/model selection UI
- richer multi-agent routing and delegation behavior beyond the default primary-agent runtime
- replacing CLI-backed providers with richer SDK implementations if later needed for more advanced streaming or tool semantics

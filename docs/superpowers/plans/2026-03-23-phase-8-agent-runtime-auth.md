# Phase 8 Agent Runtime & Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the default `breqy` agent runtime with engine-directed work dispatch, mediated tool round trips, provider-backed streaming responses, all five provider auth paths, skill loading, and private-memory runtime wiring.

**Architecture:** Extend the existing engine/A2A foundation with a typed agent-work dispatch contract and a typed tool request/result contract, then add a real `breqy/agents/` runtime that loads `agents/breqy/`, selects one configured provider/model from `agent.yaml`, streams output through Breqy-native provider adapters, and routes all credentials through a `SecretProvider`-backed `CredentialStore`. Reuse working orchestrator auth/runner patterns via Breqy-owned adapters rather than importing orchestrator contracts directly.

**Tech Stack:** Python 3.12+, pydantic v2, aiosqlite, structlog, pytest, pytest-asyncio, keyring, YAML config, existing A2A transport/tool service

---

## File Structure

- Create: `breqy/agents/__init__.py`
- Create: `breqy/agents/runtime.py`
- Create: `breqy/agents/models.py`
- Create: `breqy/agents/providers/__init__.py`
- Create: `breqy/agents/providers/base.py`
- Create: `breqy/agents/providers/adapters.py`
- Create: `breqy/agents/auth/__init__.py`
- Create: `breqy/agents/auth/models.py`
- Create: `breqy/agents/auth/service.py`
- Create: `breqy/agents/auth/adapters.py`
- Create: `breqy/agents/credentials.py`
- Create: `breqy/agents/skills.py`
- Create: `breqy/agents/private_memory.py`
- Create: `agents/breqy/agent.yaml`
- Create: `agents/breqy/persona.md`
- Create: `skills/` (top-level compatibility/canonical root for this phase)
- Modify: `breqy/config/models.py`
- Modify: `breqy/config/loader.py`
- Modify: `breqy/domain/enums.py`
- Modify: `breqy/domain/events.py`
- Modify: `breqy/domain/models.py`
- Modify: `breqy/engine/server.py`
- Modify: `breqy/engine/daemon.py`
- Modify: `breqy/engine/agent_registry.py`
- Modify: `breqy/a2a/client.py` (only if a small helper is needed for request/result waiting)
- Modify: `breqy/a2a/server.py`
- Modify: `breqy/tools/service.py` (only if event typing or invocation/result plumbing needs a narrow extension)
- Modify: `breqy/tools/memory.py` (private-memory delegated flow support)
- Modify: `breqy/memory/contracts.py` (runtime private-memory contract integration if needed)
- Modify: `docs/architecture.md`
- Modify: `docs/prd.md`
- Modify: `CHANGES.md`
- Modify: `.planning/ROADMAP.md`
- Modify: `.planning/STATE.md`
- Create: `.planning/phases/08-agent-runtime-auth/README.md`
- Create: `.planning/phases/08-agent-runtime-auth/08-SUMMARY.md`
- Create: `.planning/phases/08-agent-runtime-auth/08-VERIFICATION.md`
- Test: `tests/unit/config/test_config.py`
- Test: `tests/unit/domain/test_events.py`
- Test: `tests/unit/domain/test_models.py`
- Test: `tests/unit/engine/test_agent_registry.py`
- Test: `tests/unit/engine/test_agent_spawner.py`
- Test: `tests/unit/engine/test_server.py`
- Create Test: `tests/unit/agents/test_runtime.py`
- Create Test: `tests/unit/agents/test_credentials.py`
- Create Test: `tests/unit/agents/test_auth_service.py`
- Create Test: `tests/unit/agents/test_provider_adapters.py`
- Create Test: `tests/unit/agents/test_skill_loader.py`
- Create Test: `tests/unit/agents/test_private_memory.py`
- Create Test: `tests/integration/agents/test_runtime_roundtrip.py`
- Create Test: `tests/integration/agents/test_private_memory_flow.py`

## Phase 8 Event Contract Notes

- `AgentWorkRequestedEvent` must include at minimum:
  - `session_id`
  - `agent_id`
  - triggering `message_id`
  - current user message content
  - embedded `SessionContextBundle`
  - `active_skill_ids`
  - optional task context reference
  - correlation id for streamed response/result events
- `ToolExecutionRequestedEvent` must include at minimum:
  - `session_id`
  - `agent_id`
  - `tool_name`
  - normalized tool arguments
  - invocation/correlation identifier
- `ToolExecutionResultEvent` must include at minimum:
  - `session_id`
  - `agent_id`
  - invocation/correlation identifier
  - structured success or failure payload
- delegated private-memory events should mirror the same correlation discipline using explicit operation name, arguments, and result payload fields

### Task 1: Expand agent config and default agent definition

**Files:**
- Modify: `breqy/config/models.py`
- Modify: `breqy/config/loader.py`
- Test: `tests/unit/config/test_config.py`
- Create: `agents/breqy/agent.yaml`
- Create: `agents/breqy/persona.md`

- [ ] **Step 1: Write failing config tests for Phase 8 agent manifest fields and persona loading**

Add tests for:
- required `provider` field
- provider value validation against `copilot`, `codex`, `claude`, `gemini`, `qwen`
- required `model` field
- optional `provider_settings`
- `skill_permissions` wildcard represented as `['*']`
- `load_agent_config()` loading `persona.md`
- missing persona file failure

- [ ] **Step 2: Run targeted config tests and verify failure**

Run: `uv run pytest tests/unit/config/test_config.py -v`

Expected: FAIL for missing fields or missing persona-loading behavior.

- [ ] **Step 3: Extend `AgentConfig` and loader with minimal Phase 8 manifest support**

Implement:
- `provider: str`
- `model: str`
- `provider_settings: dict[str, str] = {}`
- normalized `skill_permissions` validation for explicit IDs or `['*']`
- loader return shape that includes resolved persona content/path without changing existing engine config behavior

- [ ] **Step 4: Create the default agent definition**

Create `agents/breqy/agent.yaml` with a single provider/model pair and explicit tool/skill permissions, and create `agents/breqy/persona.md` with the approved sharp/calm/high-agency/trustworthy tone.

- [ ] **Step 5: Re-run config tests and verify pass**

Run: `uv run pytest tests/unit/config/test_config.py -v`

Expected: PASS.

### Task 2: Add Phase 8 domain events and runtime data models

**Files:**
- Modify: `breqy/domain/enums.py`
- Modify: `breqy/domain/events.py`
- Modify: `breqy/domain/models.py`
- Create: `breqy/agents/models.py`
- Test: `tests/unit/domain/test_events.py`
- Test: `tests/unit/domain/test_models.py`

- [ ] **Step 1: Write failing domain tests for new Phase 8 contracts**

Cover:
- `AgentWorkRequestedEvent`
- `ToolExecutionRequestedEvent`
- `ToolExecutionResultEvent`
- `PrivateMemoryOperationRequestedEvent`
- `PrivateMemoryOperationResultEvent`
- typed auth/session status models if stored in domain space
- `ProviderCredential` / `SessionContextBundle` / related runtime models if housed in `breqy/agents/models.py`

- [ ] **Step 2: Run targeted domain tests and verify failure**

Run: `uv run pytest tests/unit/domain/test_events.py tests/unit/domain/test_models.py -v`

Expected: FAIL for missing event types or model contracts.

- [ ] **Step 3: Add minimal event and model contracts**

Implement exact Phase 8 contracts:
- `AgentWorkRequestedEvent` with embedded session context bundle and `active_skill_ids`
- `ToolExecutionRequestedEvent`
- `ToolExecutionResultEvent`
- `PrivateMemoryOperationRequestedEvent`
- `PrivateMemoryOperationResultEvent`
- typed provider/auth/runtime payload models needed by later tasks

- [ ] **Step 4: Re-run the domain tests and verify pass**

Run: `uv run pytest tests/unit/domain/test_events.py tests/unit/domain/test_models.py -v`

Expected: PASS.

### Task 3: Add credential store and auth service contracts

**Files:**
- Create: `breqy/agents/credentials.py`
- Create: `breqy/agents/auth/__init__.py`
- Create: `breqy/agents/auth/models.py`
- Create: `breqy/agents/auth/service.py`
- Modify: `breqy/secrets/provider.py` only if a tiny extension is needed for typed payload serialization helpers
- Create Test: `tests/unit/agents/test_credentials.py`
- Create Test: `tests/unit/agents/test_auth_service.py`

- [ ] **Step 1: Write failing tests for typed credential storage and auth service state**

Cover:
- provider-scoped credential persistence over `SecretProvider`
- structured payload round-trip for token/api-key flows
- `start()` / `get_status()` / `submit_code()` / `submit_secret()` / `revoke()` behavior
- no plain env/file credential fallback in runtime-facing APIs

- [ ] **Step 2: Run the new auth/credential tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_credentials.py tests/unit/agents/test_auth_service.py -v`

Expected: FAIL for missing modules or missing typed credential behavior.

- [ ] **Step 3: Implement `ProviderCredential`, `CredentialStore`, and auth state models**

Add minimal typed models plus serialization to the existing secret backend, keeping keys under the Breqy namespace and provider-specific keys.

- [ ] **Step 4: Implement the Breqy-native auth service interface**

Add a small orchestration service that exposes the Phase 8 backend contract without binding to any TUI code.

- [ ] **Step 5: Re-run the auth/credential tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_credentials.py tests/unit/agents/test_auth_service.py -v`

Expected: PASS.

### Task 4: Add provider auth adapters for all five providers

**Files:**
- Create: `breqy/agents/auth/adapters.py`
- Create Test: `tests/unit/agents/test_auth_service.py`

- [ ] **Step 1: Write failing tests for provider-specific auth adapter behavior**

Cover:
- Copilot device flow mapping
- Codex device flow/token exchange mapping
- Claude PKCE/code exchange mapping
- Gemini API-key mapping
- Qwen API-key mapping
- translation from reused orchestrator logic into Breqy-native `AuthStatus` / `AuthSession`

- [ ] **Step 2: Run the auth adapter tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_auth_service.py -v`

Expected: FAIL for missing provider adapters or incorrect flow typing.

- [ ] **Step 3: Implement minimal provider auth adapters**

Reuse orchestrator patterns behind Breqy-owned wrappers only. Keep external/provider-specific details inside adapters.

- [ ] **Step 4: Re-run auth tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_auth_service.py -v`

Expected: PASS.

### Task 5: Add Breqy-native provider execution adapters

**Files:**
- Create: `breqy/agents/providers/__init__.py`
- Create: `breqy/agents/providers/base.py`
- Create: `breqy/agents/providers/adapters.py`
- Create Test: `tests/unit/agents/test_provider_adapters.py`

- [ ] **Step 1: Write failing tests for `ModelProvider` and provider adapters**

Cover:
- provider/model identity
- streaming text chunk normalization
- tool-call delta normalization for at least one real provider path
- chat-only adapter behavior for providers without practical tool calls in the reused integration
- credential injection via `CredentialStore`

- [ ] **Step 2: Run provider adapter tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_provider_adapters.py -v`

Expected: FAIL for missing provider contracts or adapter behavior.

- [ ] **Step 3: Implement `ModelProvider` base contract and minimal adapters for all five providers**

Implement:
- Breqy-owned provider interface
- adapter wrappers over the proven orchestrator runner patterns
- one clearly tested tool-capable provider path using `Claude` as the required end-to-end proof provider for Phase 8
- chat-only behavior where tool-call support is not practical in Phase 8

- [ ] **Step 4: Re-run provider adapter tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_provider_adapters.py -v`

Expected: PASS.

### Task 6: Add skill loader and canonical skill-root support

**Files:**
- Create: `breqy/agents/skills.py`
- Create: `skills/`
- Create Test: `tests/unit/agents/test_skill_loader.py`

- [ ] **Step 1: Write failing tests for skill discovery, wildcard permissions, and invalid dispatch handling**

Cover:
- discovery from top-level `skills/`
- compatibility support for `system/skills/` during transition
- `skill.yaml` manifest validation
- `required_tools` checking against `tool_permissions`
- `['*']` wildcard handling
- unknown/disallowed `active_skill_ids` causing structured turn rejection

- [ ] **Step 2: Run skill-loader tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_skill_loader.py -v`

Expected: FAIL for missing loader or permission rules.

- [ ] **Step 3: Implement minimal skill loader and resolution helpers**

Add the smallest implementation that validates manifests, loads instructions, and resolves active skill IDs for runtime use.

- [ ] **Step 4: Re-run skill-loader tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_skill_loader.py -v`

Expected: PASS.

### Task 7: Add agent-owned private-memory runtime support

**Files:**
- Create: `breqy/agents/private_memory.py`
- Modify: `breqy/tools/memory.py`
- Modify: `breqy/memory/contracts.py` only if needed for runtime composition helpers
- Create Test: `tests/unit/agents/test_private_memory.py`
- Create Test: `tests/integration/agents/test_private_memory_flow.py`

- [ ] **Step 1: Write failing tests for delegated private-memory round trips**

Cover:
- engine-mediated request to private memory
- same-agent delegated execution
- result returned through engine completion path
- cross-agent rejection
- no engine ownership of private-memory records
- explicit `PrivateMemoryOperationRequestedEvent` / `PrivateMemoryOperationResultEvent` routing

- [ ] **Step 2: Run private-memory tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_private_memory.py tests/integration/agents/test_private_memory_flow.py -v`

Expected: FAIL for missing delegated runtime flow.

- [ ] **Step 3: Implement the minimal private-memory runtime store and delegated execution helpers**

Keep the store agent-owned and wire only the narrow contract required by the Phase 8 spec.

Implement the explicit delegated private-memory request/result protocol instead of overloading generic tool-result delivery.

- [ ] **Step 4: Re-run the private-memory tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_private_memory.py tests/integration/agents/test_private_memory_flow.py -v`

Expected: PASS.

### Task 8: Implement engine registration, dispatch, and tool-result routing

**Files:**
- Modify: `breqy/engine/server.py`
- Modify: `breqy/engine/agent_registry.py`
- Modify: `breqy/a2a/client.py` only if a small helper is needed
- Modify: `breqy/a2a/server.py`
- Test: `tests/unit/engine/test_agent_registry.py`
- Test: `tests/unit/engine/test_server.py`

- [ ] **Step 1: Write failing engine tests for Phase 8 routing behavior**

Cover:
- registration/lifecycle event binds `agent_id` to `client_id`
- disconnect removes registry entry
- triggering user messages are persisted into the canonical message store before dispatch
- user message produces `AgentWorkRequestedEvent` to the primary agent with an embedded `SessionContextBundle`
- engine sanitizes `active_skill_ids` before dispatch and runtime still re-validates them
- tool execution request from agent is executed by the engine
- tool execution result is sent back to the requesting agent
- completed assistant responses are persisted into the canonical message store before later turns rely on them as session context
- transient tool request/result and delegated private-memory request/result events are not persisted as extra audit-log records

- [ ] **Step 2: Run targeted engine tests and verify failure**

Run: `uv run pytest tests/unit/engine/test_agent_registry.py tests/unit/engine/test_server.py -v`

Expected: FAIL for missing routing/dispatch behavior.

- [ ] **Step 3: Implement minimal registration and dispatch logic in `EngineServer`**

Keep changes narrow:
- preserve event bus/event writer behavior
- add only the typed dispatch/request/result routing required by Phase 8
- keep invocation persistence engine-owned

More specifically:
- `EngineServer` should persist inbound user turns before building the dispatch payload so `SessionContextBundle` is always assembled from canonical stored history
- `EngineServer` should be the component that assembles the `SessionContextBundle` from canonical message history, memory summary/checkpoint data, and any current task context before dispatch
- `EngineServer` should sanitize `active_skill_ids` before dispatch so only known/permitted skills are sent to the runtime
- final assistant messages emitted by the runtime should be persisted into canonical message storage before future dispatches consume them as prior context
- transient request/result handoff events (`ToolExecutionRequestedEvent`, `ToolExecutionResultEvent`, `PrivateMemoryOperationRequestedEvent`, `PrivateMemoryOperationResultEvent`) must stay transport-only by default and must not be appended as extra durable audit-log records
- `A2AServer` should gain an explicit disconnect callback or equivalent hook so `EngineServer` can deterministically remove stale `agent_id -> client_id` registry entries when a client socket closes
- transport-only handoff events should use a non-persisted direct routing path through `A2AServer.send_to()` / targeted dispatch handling, or an equally explicit filter before `EventWriter.write`, rather than the normal publish-everything path

- [ ] **Step 4: Re-run the engine tests and verify pass**

Run: `uv run pytest tests/unit/engine/test_agent_registry.py tests/unit/engine/test_server.py -v`

Expected: PASS.

### Task 9: Implement the agent runtime loop and process entrypoint

**Files:**
- Create: `breqy/agents/runtime.py`
- Modify: `breqy/engine/daemon.py`
- Create Test: `tests/unit/agents/test_runtime.py`
- Test: `tests/unit/engine/test_agent_spawner.py`
- Test: `tests/unit/engine/test_daemon.py`

- [ ] **Step 1: Write failing runtime tests for startup, dispatch handling, and structured turn failure**

Cover:
- runtime loads config + persona
- runtime connects through `A2AClient`
- runtime handles `AgentWorkRequestedEvent`
- runtime validates active skills
- invalid skill ID rejects the turn with a structured error event
- runtime emits streamed chunks and final response events

- [ ] **Step 2: Run the runtime and spawner tests and verify failure**

Run: `uv run pytest tests/unit/agents/test_runtime.py tests/unit/engine/test_agent_spawner.py tests/unit/engine/test_daemon.py -v`

Expected: FAIL for missing runtime entrypoint or missing dispatch behavior.

- [ ] **Step 3: Implement the minimal runtime loop**

Implement:
- CLI entrypoint compatible with `AgentSpawner`
- engine connect/listen loop
- provider turn orchestration
- typed tool request/result handling
- skill activation handling
- final assistant message emission compatible with canonical message persistence on the engine side

- [ ] **Step 4: Wire default-agent startup/shutdown into `EngineDaemon`**

Implement the smallest daemon/runtime composition needed so the engine can source the default agent from `agents/breqy/` and stop it cleanly with the server lifecycle. Update tests away from the old `system/agents/breqy` assumption where needed.

- [ ] **Step 5: Re-run the runtime, spawner, and daemon tests and verify pass**

Run: `uv run pytest tests/unit/agents/test_runtime.py tests/unit/engine/test_agent_spawner.py tests/unit/engine/test_daemon.py -v`

Expected: PASS.

### Task 10: Verify full runtime round trip with integration tests

**Files:**
- Create Test: `tests/integration/agents/test_runtime_roundtrip.py`
- Create Test: `tests/integration/agents/test_private_memory_flow.py`
- Test: `tests/unit/agents/test_provider_adapters.py`
- Test: `tests/unit/agents/test_runtime.py`
- Test: `tests/unit/engine/test_server.py`

- [ ] **Step 1: Write failing integration tests for end-to-end Phase 8 flows**

Cover:
- spawned runtime registers with engine
- engine routes a user turn to the primary agent
- runtime streams a response from a provider double through the typed event path
- tool-calling provider path completes the full mediated loop
- credentials created through the auth service are the credentials consumed by the provider adapter, with no env/file fallback on the execution path
- private-memory delegated flow succeeds for the owning agent and fails for another agent

- [ ] **Step 2: Run the integration tests and verify failure**

Run: `uv run pytest tests/integration/agents/test_runtime_roundtrip.py tests/integration/agents/test_private_memory_flow.py -v`

Expected: FAIL for missing end-to-end wiring.

- [ ] **Step 3: Fill only the minimal gaps surfaced by integration failures**

Do not widen scope beyond Phase 8. Keep fixes focused on runtime, routing, provider orchestration, and private-memory delegation.

- [ ] **Step 4: Re-run the integration tests and verify pass**

Run: `uv run pytest tests/integration/agents/test_runtime_roundtrip.py tests/integration/agents/test_private_memory_flow.py -v`

Expected: PASS.

### Task 11: Documentation, planning artifacts, and verification

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/prd.md`
- Modify: `CHANGES.md`
- Modify: `.planning/ROADMAP.md`
- Modify: `.planning/STATE.md`
- Create: `.planning/phases/08-agent-runtime-auth/README.md`
- Create: `.planning/phases/08-agent-runtime-auth/08-SUMMARY.md`
- Create: `.planning/phases/08-agent-runtime-auth/08-VERIFICATION.md`
- Test: `tests/unit/config/test_config.py`
- Test: `tests/unit/domain/test_events.py`
- Test: `tests/unit/domain/test_models.py`
- Test: `tests/unit/engine/test_agent_registry.py`
- Test: `tests/unit/engine/test_agent_spawner.py`
- Test: `tests/unit/engine/test_server.py`
- Test: `tests/unit/agents/test_runtime.py`
- Test: `tests/unit/agents/test_credentials.py`
- Test: `tests/unit/agents/test_auth_service.py`
- Test: `tests/unit/agents/test_provider_adapters.py`
- Test: `tests/unit/agents/test_skill_loader.py`
- Test: `tests/unit/agents/test_private_memory.py`
- Test: `tests/integration/agents/test_runtime_roundtrip.py`
- Test: `tests/integration/agents/test_private_memory_flow.py`

- [ ] **Step 1: Update docs for Phase 8 runtime/auth decisions**

Include:
- new agent runtime dispatch path
- new event types
- canonical `agents/breqy/` and top-level `skills/`
- Gemini API-key decision
- provider-scoped credential handling

- [ ] **Step 2: Run the targeted Phase 8 test set and verify pass**

Run: `uv run pytest tests/unit/config/test_config.py tests/unit/domain/test_events.py tests/unit/domain/test_models.py tests/unit/engine/test_agent_registry.py tests/unit/engine/test_agent_spawner.py tests/unit/engine/test_server.py tests/unit/agents/test_runtime.py tests/unit/agents/test_credentials.py tests/unit/agents/test_auth_service.py tests/unit/agents/test_provider_adapters.py tests/unit/agents/test_skill_loader.py tests/unit/agents/test_private_memory.py tests/integration/agents/test_runtime_roundtrip.py tests/integration/agents/test_private_memory_flow.py -v`

Expected: PASS.

- [ ] **Step 3: Run the full suite and verify pass**

Run: `uv run pytest -q`

Expected: full project pass.

- [ ] **Step 4: Run focused coverage verification for Phase 8 business-logic files**

Run a focused coverage command covering new agent runtime/auth/provider/skill/private-memory modules and confirm repository thresholds are met, especially 100% for business logic.

- [ ] **Step 5: Record exact verification evidence**

Capture:
- exact targeted test commands
- full-suite result
- exact coverage command and results
- phase completion notes in `.planning/phases/08-agent-runtime-auth/08-VERIFICATION.md`

- [ ] **Step 6: Capture phase summary and state updates**

Update:
- `.planning/phases/08-agent-runtime-auth/08-SUMMARY.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `CHANGES.md`

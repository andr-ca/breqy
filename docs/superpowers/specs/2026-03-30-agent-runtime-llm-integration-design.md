# Agent Runtime & LLM Integration Design (Slice 1)

**Date:** 2026-03-30
**Phase:** 4 -- Agent Runtime + LLM Integration
**Supersedes:** Relevant sections of `2026-03-23-phase-8-agent-runtime-auth-design.md` (scoped down to 2 providers for Slice 1)

## Goal

Make the breqy agent runtime produce actual AI responses. Today the agent process loads config and exits immediately. After this work, a user message in the TUI will flow through the engine to the agent, which calls an LLM, streams the response back, handles tool calls, and delivers a complete assistant message.

## Scope

This design covers:
- `ModelProvider` abstraction with streaming and tool-call support
- Two provider implementations: GitHub Copilot and OpenAI Codex (ChatGPT Plus/Pro)
- Device flow authentication for both providers
- Full agent runtime A2A loop (connect, listen, dispatch, respond)
- Work handler with inference loop and tool call cycling
- Message assembly from `SessionContextBundle` to OpenAI-format messages
- Tool schema generation from `ToolRegistry`
- CLI auth commands (`breqy auth copilot`, `breqy auth codex`)

This design does not cover:
- Claude, Gemini, or Qwen providers (deferred to later phases)
- Skill loader and skill-aware prompt injection
- Private memory runtime boundary
- TUI auth panel
- Model selection UI (Phase 6)

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| HTTP client | `httpx` | Async-native, lightweight, built-in streaming. No SDK overhead. |
| API format | OpenAI Chat Completions | Both Copilot and Codex expose OpenAI-compatible APIs. |
| Auth flows | Device code only | breqy is a terminal app; no browser redirect needed. |
| Token storage | Existing `SecretProvider` | Reuse keyring/file/env chain already built. |
| Second provider | OpenAI Codex (ChatGPT Plus/Pro) | Validates multi-provider abstraction with different auth flow. |

## Architecture

### Approach

Thin provider layer with direct `httpx` calls against OpenAI-compatible APIs. Each provider is a class that knows its base URL, auth headers, and quirks. Auth is handled by separate `AuthManager` implementations. The agent runtime connects to the engine via A2A, listens for work events, calls the provider, and streams responses back.

### Component diagram

```
Engine                          Agent Process
  |                                |
  |--AgentWorkRequestedEvent------>|
  |                                |-- build_messages(SessionContextBundle)
  |                                |-- provider.stream(messages, tools, model)
  |<---MessageChunkEvent-----------|   (text delta)
  |<---MessageChunkEvent-----------|   (text delta)
  |                                |   finish_reason="tool_calls"
  |<---ToolExecutionRequestedEvent-|
  |                                |
  |  (engine runs policy+tool)     |
  |                                |
  |--ToolExecutionResultEvent----->|
  |                                |-- append tool result to messages
  |                                |-- provider.stream(messages, tools, model)  [loop]
  |<---MessageChunkEvent-----------|
  |<---MessageSentEvent(ASSISTANT)-|   finish_reason="stop"
```

## Section 1: ModelProvider Interface

### `breqy/models/provider.py`

```python
class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ToolCallDelta(BaseModel):
    index: int
    id: str | None = None
    name: str | None = None
    arguments_fragment: str | None = None

class StreamChunk(BaseModel):
    text: str | None = None
    tool_calls: list[ToolCallDelta] | None = None
    finish_reason: str | None = None
    usage: UsageInfo | None = None

class CompletionResult(BaseModel):
    content: str
    tool_calls: list[dict] | None = None
    finish_reason: str
    usage: UsageInfo

class ModelProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamChunk]: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult: ...

    @abstractmethod
    async def list_models(self) -> list[ModelEntry]: ...

    @abstractmethod
    def provider_id(self) -> str: ...
```

### `breqy/models/sse.py`

Shared async SSE parser for `httpx` streaming responses. Parses `data: {...}\n\n` format, yields parsed JSON dicts, handles `data: [DONE]` sentinel. Approximately 50 lines. Assembles multi-line `data:` fields per the SSE spec.

### `breqy/models/copilot.py` -- CopilotProvider

- Base URL: `https://api.githubcopilot.com`
- Endpoint: `POST /chat/completions`
- Required headers:
  - `Authorization: Bearer <gho_token>`
  - `User-Agent: breqy/<version>`
  - `Openai-Intent: conversation-edits`
- Streaming: standard OpenAI SSE with `stream: true`
- Tool calls: standard OpenAI function calling format
- Auth: delegates to `CopilotAuthManager`

### `breqy/models/codex.py` -- CodexProvider

- All requests go to: `https://chatgpt.com/backend-api/codex/responses`
- API format: OpenAI Chat Completions compatible (same request body shape as Copilot: `messages`, `tools`, `stream`, `model` fields; same SSE streaming response format with `choices[].delta`)
- Required headers:
  - `Authorization: Bearer <access_token>`
  - `ChatGPT-Account-Id: <account_id>` (from JWT)
  - `originator: breqy`
  - `User-Agent: breqy/<version>`
- Token refresh: auto-refresh when `expires_at < time.time()`
- Auth: delegates to `CodexAuthManager`

## Section 2: Authentication System

### `breqy/models/auth.py`

```python
class TokenInfo(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: float = 0.0
    account_id: str | None = None

class AuthManager(ABC):
    @abstractmethod
    async def get_token(self) -> TokenInfo: ...

    @abstractmethod
    async def authenticate(self) -> TokenInfo: ...

    @abstractmethod
    def is_authenticated(self) -> bool: ...
```

Token storage: JSON-serialized `TokenInfo` stored via `SecretProvider` under provider-specific keys (`copilot_token`, `codex_token`).

### `breqy/models/auth_copilot.py` -- GitHub Device Flow

1. `POST https://github.com/login/device/code` with `client_id=Ov23li8tweQw6odWQebz`, `scope=read:user`
2. Display `user_code`, user visits `github.com/login/device`
3. Poll `POST https://github.com/login/oauth/access_token` with `device_code` at `interval`
4. Handle `authorization_pending` (retry), `slow_down` (+5s), errors
5. Store `gho_*` token via SecretProvider; `expires_at=0` (no expiry)

### `breqy/models/auth_codex.py` -- OpenAI Headless Device Flow

1. `POST https://auth.openai.com/api/accounts/deviceauth/usercode` with `client_id=app_EMoamEEZ73f0CkXaXp7hrann`
2. Display `user_code`, user visits `https://auth.openai.com/codex/device`
3. Poll `POST https://auth.openai.com/api/accounts/deviceauth/token` -> `authorization_code` + `code_verifier`
4. Exchange at `POST https://auth.openai.com/oauth/token` with `grant_type=authorization_code`
5. Parse JWT `id_token` to extract `account_id` (decode payload with `base64` + `json`, no signature verification)
6. Store token via SecretProvider; track `expires_at` from `expires_in`
7. Auto-refresh: `POST https://auth.openai.com/oauth/token` with `grant_type=refresh_token` when expired

### CLI Commands

- `breqy auth copilot` -- runs CopilotAuthManager.authenticate()
- `breqy auth codex` -- runs CodexAuthManager.authenticate()
- Both print status messages and the device code for the user

## Section 3: Agent Runtime -- A2A Loop & Work Handler

### `breqy/agents/runtime.py` -- Rewrite

**Startup sequence:**
1. Parse args (`--agent-dir`, `--engine-socket`, `--session-id`)
2. Load agent config (provider, model, persona, tool_permissions)
3. Initialize `ModelProvider` based on `config.provider`
4. Check `auth_manager.is_authenticated()` -- fail fast with clear error if not
5. Create `A2AClient`, connect to engine socket
6. Send `AgentLifecycleEvent(AGENT_CONNECTED)`
7. Enter listen loop: `async for envelope in client.listen()`

**Event dispatch:**

| Event | Handler |
|---|---|
| `AGENT_WORK_REQUESTED` | `_handle_work()` |
| `CONTROL_STOP` | `_handle_stop()` |
| `CONTROL_STOP_AND_STEER` | `_handle_stop_and_steer()` (stop current generation, then steer with new instructions) |
| `CONTROL_STEER` | `_handle_steer()` |
| `CONTROL_CIRCUIT_BREAK` | `_handle_circuit_break()` |
| `TOOL_EXECUTION_RESULT` | `_handle_tool_result()` |
| `MODEL_LIST_REQUESTED` | `_handle_model_list()` |
| `MODEL_SWITCH_REQUESTED` | `_handle_model_switch()` |

Disconnect/error: send `AgentLifecycleEvent(AGENT_DISCONNECTED)`, exit.

**Outbound event requirements:** The runtime must set `agent_id` and `session_id` on every event it emits (these are base `Event` fields that default to empty string). The runtime knows its `agent_id` from config and the `session_id` from the work event.

### `_handle_work(event)` -- Inference Loop

1. Build messages from `SessionContextBundle` via `prompt.build_messages()`
2. Build tool schemas from `ToolRegistry` via `tool_schemas.build_tool_schemas()`
3. Call `provider.stream(messages, tools=tools, model=config.model)`
4. For each `StreamChunk`:
   - `text` present: send `MessageChunkEvent` to engine via A2A
   - `tool_calls` present: accumulate fragments
   - `finish_reason="tool_calls"`:
     - For each complete tool call: send `ToolExecutionRequestedEvent` to engine
     - Wait for `ToolExecutionResultEvent` (via per-invocation-id `asyncio.Future`)
     - Append assistant message (with tool_calls) and tool results to local messages
     - Loop back to step 3
   - `finish_reason="stop"`:
     - Send `MessageSentEvent(role=ASSISTANT, content=full_response)` to engine
     - Done
5. Max tool iterations: 25 (configurable). If exceeded, send partial response.

**Error handling:**
- HTTP 401/403: log auth error, suggest `breqy auth <provider>`
- HTTP 429: exponential backoff (1s, 2s, 4s), 3 retries max, then error
- Network/other: log error, send error message to engine

**Cancellation:** `_cancelled` asyncio.Event set by stop/circuit-break handlers. Checked between chunks and between tool iterations. On cancel, send partial response as final message.

### Tool result delivery

Tool results arrive as events on the A2A listen stream. The runtime maintains a dict of `{invocation_id: asyncio.Future}`. When `_handle_work()` sends a tool request, it creates a Future keyed by the invocation ID. When `_handle_tool_result()` fires, it resolves the matching Future. The work handler awaits the Future to get the result.

## Section 4: Message Assembly & Tool Schemas

### `breqy/agents/prompt.py`

```python
def build_messages(
    persona: str,
    session_context: SessionContextBundle,
    user_message: str,
) -> list[dict]:
```

**System message structure:**
```
[persona content]

---

## Session Memory
[memory_summary if non-empty]

## Memory Checkpoint
[memory_checkpoint if non-empty]

## Global Memory
[For each record: - [kind]: content (tags)]

## Active Task
[If task_context: Task: title (status) + summary]
```

**History messages:** Direct mapping from `session_context.messages`:
- `Message(role=USER)` -> `{"role": "user", "content": msg.content}`
- `Message(role=ASSISTANT)` -> `{"role": "assistant", "content": msg.content}`

**Tool call messages** (local to inference loop, not persisted until final response):
- `{"role": "assistant", "content": null, "tool_calls": [...]}`
- `{"role": "tool", "tool_call_id": "...", "content": "..."}`

### `breqy/agents/tool_schemas.py`

```python
def build_tool_schemas(
    tool_registry: ToolRegistry,
    permitted_tools: list[str],
) -> list[dict]:
```

Maps ToolRegistry entries to OpenAI function-calling format using Pydantic `.model_json_schema()`:
```json
{
  "type": "function",
  "function": {
    "name": "shell_execute",
    "description": "...",
    "parameters": { "..." }
  }
}
```

## Section 5: File Layout & Dependencies

### New files

```
breqy/models/
  __init__.py              # Re-exports ModelProvider, get_provider()
  provider.py              # ModelProvider ABC, StreamChunk, CompletionResult, UsageInfo
  sse.py                   # Shared SSE parser for httpx streaming responses
  copilot.py               # CopilotProvider(ModelProvider)
  codex.py                 # CodexProvider(ModelProvider)
  auth.py                  # AuthManager ABC, TokenInfo model
  auth_copilot.py          # CopilotAuthManager (GitHub device flow)
  auth_codex.py            # CodexAuthManager (OpenAI headless device flow)

breqy/agents/
  prompt.py                # Message assembly from SessionContextBundle
  tool_schemas.py          # ToolRegistry to OpenAI function schemas
```

### Modified files

```
breqy/agents/runtime.py   # REWRITE: full A2A loop + work handler
breqy/agents/__init__.py   # Re-export runtime entry point
breqy/cli.py               # Add `breqy auth copilot` and `breqy auth codex`
pyproject.toml              # Add httpx dependency
```

### New dependency

`httpx` -- async HTTP client with streaming support. No other new dependencies. JWT payload decoding uses stdlib `base64` + `json`.

### Test files

```
tests/unit/models/
  test_provider.py          # ABC contract tests
  test_sse.py               # SSE parser unit tests
  test_copilot.py           # CopilotProvider tests (httpx mocked)
  test_codex.py             # CodexProvider tests (httpx mocked)
  test_auth_copilot.py      # Device flow tests (httpx mocked)
  test_auth_codex.py        # Device flow + token refresh tests

tests/unit/agents/
  test_runtime.py           # A2A loop + work handler tests
  test_prompt.py            # Message assembly tests
  test_tool_schemas.py      # Schema generation tests

tests/integration/
  test_agent_inference.py   # End-to-end: engine -> agent -> mock LLM -> response
```

## Error Handling

| Error | Behavior |
|---|---|
| Auth not configured | Agent exits on startup with clear message: `Run 'breqy auth <provider>' first` |
| HTTP 401/403 | Log auth error, suggest re-auth, send error message to engine |
| HTTP 429 | Exponential backoff (1s, 2s, 4s), 3 retries max, then error |
| Network error | Log, send error message to engine, agent stays alive for next request |
| Malformed SSE | Log warning, skip chunk, continue |
| Tool loop > 25 iterations | Send partial response, log warning |
| Cancellation (stop/circuit-break) | Send partial response, reset state for next request |

## Testing Strategy

All new files require 100% unit test coverage per repository rules. Tests use:
- `httpx` mocking (via `httpx.MockTransport` or `respx`) for provider and auth tests
- `AsyncMock` for A2A client in runtime tests
- Deterministic provider doubles for integration tests
- No live provider accounts required

## Risks

| Risk | Mitigation |
|---|---|
| Copilot API changes auth requirements | Device flow uses public GitHub OAuth; stable for years |
| Codex device flow is undocumented/unstable | Follows same flow as OpenCode which has wide adoption |
| Tool call loop divergence between providers | Both use identical OpenAI function calling format |
| httpx streaming edge cases | SSE parser has dedicated unit tests with malformed input |

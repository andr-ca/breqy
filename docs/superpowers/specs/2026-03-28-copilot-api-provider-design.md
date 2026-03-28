# GitHub Copilot API Provider Design

**Date:** 2026-03-28
**Status:** Approved
**Scope:** Replace subprocess-based `gh copilot suggest` provider with a direct HTTP API client using GitHub OAuth device flow authentication.

## Problem

The current copilot provider (`_ConfiguredCopilotRunner` in `adapters.py`) shells out to `gh copilot suggest` as a subprocess. This command requires the `gh copilot` CLI extension, which is not installed on the developer's system. More fundamentally, the subprocess approach is fragile and provides no tool call support, no streaming granularity, and no structured error handling.

## Approach

Implement a pure Python HTTP client that:

1. Authenticates via the GitHub OAuth device flow (same approach as OpenCode).
2. Calls the GitHub Copilot chat completions API directly over HTTPS.
3. Parses SSE streaming responses into `ProviderEvent` objects.
4. Supports tool calls from day one (OpenAI-compatible function calling format).

This is the first API-based provider in Breqy. Claude stays subprocess-based (its subscription OAuth is proprietary). Other providers (OpenAI, Gemini) may be migrated to API-based in the future using patterns established here.

## Authentication Layer

### Component: `CopilotAuthenticator`

**File:** `breqy/agents/providers/copilot_auth.py`

Handles the GitHub OAuth device flow and token persistence.

### Device flow

Uses the well-known Copilot OAuth client ID `Ov23li8tweQw6odWQebz` (same as OpenCode, copilot.vim, copilot.el). The flow is:

1. `POST https://github.com/login/device/code` with `client_id` and `scope=read:user`.
2. Response contains `user_code`, `verification_uri` (`https://github.com/login/device`), `device_code`, `interval`.
3. User visits the verification URI and enters the user code.
4. Provider polls `POST https://github.com/login/oauth/access_token` with `client_id`, `device_code`, and `grant_type=urn:ietf:params:oauth:grant-type:device_code` at the specified interval.
5. Polling handles `authorization_pending` (keep waiting), `slow_down` (add 5s to interval per RFC 8628), `expired_token` (abort), `access_denied` (abort).
6. On success, receives `access_token` (GitHub OAuth token).

### Token storage

The OAuth token is stored via Breqy's existing `CredentialStore` as a `ProviderCredential`:

```python
ProviderCredential(
    provider="copilot",
    credential_kind=CredentialKind.ACCESS_TOKEN,
    secret_value=SecretStr(access_token),
    metadata={"auth_flow": "device"},
)
```

No separate Copilot token exchange is needed. The GitHub OAuth token from the device flow is sent directly as `Authorization: Bearer <token>` to the Copilot API (confirmed by OpenCode's implementation).

### Token lifecycle

GitHub OAuth tokens from the device flow do not expire unless revoked. No refresh logic is needed. On 401 from the API, the provider clears the stored token and triggers re-authentication.

### Interface

```python
class CopilotAuthenticator:
    GITHUB_CLIENT_ID: str = "Ov23li8tweQw6odWQebz"
    DEVICE_CODE_URL: str = "https://github.com/login/device/code"
    ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    OAUTH_SCOPE: str = "read:user"
    POLLING_SAFETY_MARGIN_S: float = 3.0

    def __init__(self, credential_store: CredentialStore) -> None: ...

    def get_token(self) -> str | None:
        """Retrieve stored OAuth token, or None if not authenticated."""

    def start_device_flow(self) -> DeviceFlowInfo:
        """Initiate device flow. Returns user_code + verification_uri for display."""

    def poll_for_token(self, device_code: str, interval: int) -> str:
        """Block-poll until user authorizes. Returns the OAuth access token.
        Raises CopilotAuthError on timeout/denial."""

    def clear_token(self) -> None:
        """Remove stored token (used on 401 to force re-auth)."""
```

```python
class DeviceFlowInfo(BaseModel):
    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int
```

### Error type

```python
class CopilotAuthError(Exception):
    """Raised when device flow fails (expired, denied, network error)."""
```

## API Client

### Component: `CopilotApiClient`

**File:** `breqy/agents/providers/copilot_client.py`

Handles streaming HTTP communication with the GitHub Copilot chat completions endpoint.

### Endpoint

`POST https://api.githubcopilot.com/chat/completions`

### Request format

Standard OpenAI chat completions format:

```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": true,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {"type": "object", "properties": {...}}
      }
    }
  ]
}
```

### Request headers

These headers match what OpenCode and other Copilot clients send. `Openai-Intent` and `x-initiator` are undocumented by GitHub but are used by all known Copilot clients (VS Code, OpenCode, copilot.vim).

```
Authorization: Bearer <oauth_token>
Content-Type: application/json
User-Agent: breqy/<version>
Openai-Intent: conversation-edits
x-initiator: user
Accept: text/event-stream
```

### Response format (SSE)

The response is `text/event-stream`. Each `data:` line contains an OpenAI-format JSON chunk:

```
data: {"choices":[{"delta":{"role":"assistant"},"index":0}]}
data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123","function":{"name":"read_file","arguments":""}}]},"index":0}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"path\":"}}]},"index":0}]}
data: {"choices":[{"delta":{},"finish_reason":"stop","index":0}]}
data: [DONE]
```

### SSE parsing

Implemented inline (no external library). Logic:

1. Read response body as streaming text via `httpx` response line iterator.
2. Buffer partial lines until a complete SSE event is assembled (delimited by blank lines).
3. For each event, extract lines starting with `data: `.
4. Skip `data: [DONE]` (end of stream).
5. Parse remaining `data:` lines as JSON.
6. Extract `choices[0].delta` for content/tool_calls.

Note: httpx delivers data as arbitrary byte chunks that don't align with SSE event boundaries. The implementation must buffer partial lines across chunks.

### Error handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 401 | Token expired/invalid | Clear token via `CopilotAuthenticator.clear_token()`, raise `CopilotAuthError` |
| 403 | No Copilot subscription or scope issue | Raise `CopilotApiError` with descriptive message |
| 429 | Rate limited | Respect `Retry-After` header, raise `CopilotApiError` |
| 5xx | Server error | Raise `CopilotApiError` |

### Interface

```python
class CopilotApiClient:
    BASE_URL: str = "https://api.githubcopilot.com"

    def __init__(self, http_client: httpx.Client | None = None) -> None: ...

    def stream_chat(
        self,
        *,
        token: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream chat completions. Yields parsed SSE chunk dicts.
        Raises CopilotApiError on HTTP errors."""
```

### Error type

```python
class CopilotApiError(Exception):
    """Raised on API-level errors (HTTP 4xx/5xx)."""
    status_code: int
    message: str
```

## Provider Integration

### Component: `CopilotProvider`

**File:** `breqy/agents/providers/copilot.py`

Implements `ModelProvider` ABC, wiring the auth and API client together.

### Message format conversion

Breqy's `ProviderRequest` has a `prompt: str` field. The provider converts this to OpenAI messages format:

```python
messages = [{"role": "user", "content": request.prompt}]
```

If a system persona is available (from `AgentConfig.persona_content`), it is prepended:

```python
messages = [
    {"role": "system", "content": persona},
    {"role": "user", "content": request.prompt},
]
```

The persona is passed via `ProviderRequest.extra_env` with key `BREQY_PERSONA`. This avoids modifying the `ProviderRequest` model or the `ModelProvider` interface. Note: the `AgentRuntime` must be updated to populate `extra_env["BREQY_PERSONA"]` from `AgentConfig.persona_content` when constructing `ProviderRequest`.

### SSE-to-ProviderEvent mapping

| SSE chunk field | ProviderEvent |
|---|---|
| `delta.content` (non-empty string) | `ProviderEvent(kind="text", text=content)` |
| `delta.tool_calls[i]` with `id` + `function.name` | `ProviderEvent(kind="tool_call", tool_call=ToolCallDelta(call_id=id, tool_name=name))` |
| `delta.tool_calls[i]` with `function.arguments` | `ProviderEvent(kind="tool_call", tool_call=ToolCallDelta(call_id=..., tool_name=..., arguments_chunk=args))` |
| `finish_reason="stop"` or `[DONE]` | `ProviderEvent(kind="complete", metadata=CompletionMetadata(..., exit_code=0))` |

### `exit_code` convention for API providers

`CompletionMetadata.exit_code` was designed for subprocess providers where a process exit code always exists. For HTTP API providers, the convention is:

- `exit_code=0` — successful completion (stream finished normally)
- `exit_code=1` — API error (HTTP 4xx/5xx, network error, auth failure)

### Tool definition conversion

Breqy's `ToolDefinition` maps to OpenAI's tool format:

```python
{
    "type": "function",
    "function": {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    },
}
```

### Auth flow during stream

1. Call `authenticator.get_token()`.
2. If no token, call `authenticator.start_device_flow()` and log instructions, then `authenticator.poll_for_token()`.
3. Call `client.stream_chat()` with the token.
4. If `CopilotAuthError` with 401, call `authenticator.clear_token()` and retry once.
5. Map SSE chunks to `ProviderEvent`s and yield.

### Interface

```python
class CopilotProvider(ModelProvider):
    def __init__(
        self,
        *,
        model_id: str,
        authenticator: CopilotAuthenticator,
        client: CopilotApiClient,
    ) -> None: ...

    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def model_id(self) -> str: ...

    @property
    def supports_tool_calls(self) -> bool:
        return True

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]: ...
```

## Factory Integration

### Modified: `breqy/agents/providers/adapters.py`

The `build_model_providers()` function's `"copilot"` branch changes from:

```python
elif provider_id == "copilot":
    providers[provider_id] = _ChatOnlyRunnerProvider(
        provider_id=provider_id,
        model_id=model_id,
        runner=runner_factory.make_copilot_runner(),
        runner_factory=runner_factory,
    )
```

To:

```python
elif provider_id == "copilot":
    from breqy.agents.providers.copilot import CopilotProvider
    from breqy.agents.providers.copilot_auth import CopilotAuthenticator
    from breqy.agents.providers.copilot_client import CopilotApiClient

    authenticator = CopilotAuthenticator(credential_store)
    client = CopilotApiClient()
    providers[provider_id] = CopilotProvider(
        model_id=model_id,
        authenticator=authenticator,
        client=client,
    )
```

The `_ConfiguredCopilotRunner` class and its `make_copilot_runner()` factory method become dead code and are removed. The `CopilotRunner` import from `system.orchestrator` is also removed (one fewer coupling to the old system). The `GITHUB_COPILOT_TOKEN` entry in `_PROVIDER_AUTH_ENV_VARS` is also removed since the new provider uses device-flow OAuth, not environment variable tokens.

## File Layout

### New files

| File | Purpose | Approx lines |
|---|---|---|
| `breqy/agents/providers/copilot_auth.py` | `CopilotAuthenticator`, `DeviceFlowInfo`, `CopilotAuthError` | ~120 |
| `breqy/agents/providers/copilot_client.py` | `CopilotApiClient`, `CopilotApiError`, SSE parsing | ~100 |
| `breqy/agents/providers/copilot.py` | `CopilotProvider(ModelProvider)` | ~100 |
| `tests/unit/agents/providers/test_copilot_auth.py` | Auth unit tests | ~200 |
| `tests/unit/agents/providers/test_copilot_client.py` | API client unit tests | ~150 |
| `tests/unit/agents/providers/test_copilot.py` | Provider unit tests | ~150 |

### Modified files

| File | Change |
|---|---|
| `breqy/agents/providers/adapters.py` | Replace copilot branch in `build_model_providers()`, remove `_ConfiguredCopilotRunner` and `make_copilot_runner()`, remove `CopilotRunner` import |

## Testing Strategy

All tests use mocked HTTP (no real API calls). TDD: tests written first, then implementation.

### Auth tests (`test_copilot_auth.py`)

- `test_start_device_flow_success` -- mock POST returns device code + user code
- `test_start_device_flow_http_error` -- mock POST returns 500, raises `CopilotAuthError`
- `test_poll_for_token_immediate_success` -- mock POST returns access_token on first poll
- `test_poll_for_token_pending_then_success` -- mock returns `authorization_pending` then `access_token`
- `test_poll_for_token_slow_down` -- mock returns `slow_down`, verify interval increases by 5s
- `test_poll_for_token_expired` -- mock returns `expired_token`, raises `CopilotAuthError`
- `test_poll_for_token_denied` -- mock returns `access_denied`, raises `CopilotAuthError`
- `test_get_token_from_store` -- pre-populated credential store returns token
- `test_get_token_empty_store` -- empty store returns None
- `test_clear_token` -- verify credential store delete is called

### Client tests (`test_copilot_client.py`)

- `test_stream_text_deltas` -- mock SSE with text content chunks, verify parsed dicts
- `test_stream_tool_call` -- mock SSE with tool_calls delta, verify parsed dicts
- `test_stream_done_termination` -- mock SSE ending with `data: [DONE]`, verify iterator ends
- `test_stream_401_raises_auth_error` -- mock 401 response, raises `CopilotApiError` with status 401
- `test_stream_403_raises_api_error` -- mock 403, raises `CopilotApiError`
- `test_stream_429_raises_api_error` -- mock 429, raises `CopilotApiError`
- `test_stream_empty_response` -- mock empty SSE stream, verify clean termination
- `test_stream_partial_chunks` -- mock SSE data split across multiple buffer reads, verify correct reassembly

### Provider tests (`test_copilot.py`)

- `test_stream_text_events` -- mock auth + client, verify `ProviderEvent(kind="text")` sequence
- `test_stream_tool_call_events` -- mock tool call chunks, verify `ProviderEvent(kind="tool_call")` with `ToolCallDelta`
- `test_stream_complete_event` -- verify `ProviderEvent(kind="complete")` with metadata
- `test_tool_definition_conversion` -- verify `ToolDefinition` maps to OpenAI tool format
- `test_message_format_conversion` -- verify prompt becomes `[{"role": "user", "content": ...}]`
- `test_auth_retry_on_401` -- mock first call 401, clear token, retry succeeds
- `test_no_token_triggers_device_flow` -- mock empty store, verify device flow is initiated
- `test_provider_properties` -- verify `provider_id`, `model_id`, `supports_tool_calls`

## What We Are NOT Building

- No TUI-integrated auth flow (device flow instructions go to structlog; TUI auth screen is future work)
- No token refresh (GitHub OAuth tokens don't expire)
- No GitHub Enterprise support (just `github.com`)
- No vision/image support (text-only)
- No conversation history management (single request/response; multi-turn is an engine concern)
- No retry logic beyond single 401 re-auth (no exponential backoff, no retry on 5xx)
- No migration of other providers (Claude stays subprocess; Gemini/OpenAI are future work)

## Dependencies

- `httpx>=0.27` (already in `pyproject.toml`)
- No new dependencies required

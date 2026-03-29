# Provider/Model Display & Runtime Switching Design

**Date:** 2026-03-29
**Status:** Approved
**Scope:** Display the current provider/model in the TUI `AgentStatusBar`, populate `ModelSelectScreen` with dynamically discovered models, and enable mid-conversation provider/model switching via new A2A events.

## Problem

The TUI has no visibility into which LLM provider and model the agent is using. The `AgentStatusBar` only shows connection status (connected/disconnected). A `ModelSelectScreen` exists at `ctrl+m` but is an empty shell — pushed with no model data, and its `ModelSelected` message is unhandled. Users cannot see or change the active model without editing `agent.yaml` and restarting the agent.

## Requirements

| # | Requirement | Decision |
|---|---|---|
| R1 | Display current provider and model in `AgentStatusBar` | Top of `ChatScreen`, next to agent connection status |
| R2 | Open model selector via `ctrl+m` | Populate existing `ModelSelectScreen` with discovered models |
| R3 | Runtime switching — mid-conversation | New model continues the same chat history |
| R4 | Dynamic model discovery | Query provider APIs where available; hardcoded fallback otherwise |
| R5 | Show all 5 providers | Auth on demand if user picks unauthenticated provider |
| R6 | Ephemeral switching | Runtime switch is session-only; `agent.yaml` is not mutated |

## Approach

### New A2A Event Types (4)

Add to `breqy/domain/enums.py` `EventType`:

```python
MODEL_INFO = "model.info"
MODEL_LIST_REQUESTED = "model.list.requested"
MODEL_LIST_RESPONSE = "model.list.response"
MODEL_SWITCH_REQUESTED = "model.switch.requested"
```

### New Event Classes

Add to `breqy/domain/events.py`:

#### `ModelInfoEvent`

Sent by agent → engine → TUI whenever the active model changes (on connect, after switch).

```python
class ModelInfoEvent(FixedEventTypeEvent):
    """Agent announces its current provider and model."""
    event_type: EventType = EventType.MODEL_INFO
    provider_id: str       # e.g. "copilot"
    model_id: str          # e.g. "gpt-4o"
```

#### `ModelListRequestedEvent`

Sent by TUI → engine → agent. Asks the agent to discover available models.

```python
class ModelListRequestedEvent(FixedEventTypeEvent):
    """TUI asks agent for available models across all providers."""
    event_type: EventType = EventType.MODEL_LIST_REQUESTED
```

#### `ModelListResponseEvent`

Sent by agent → engine → TUI. Returns discovered models.

```python
class ModelListResponseEvent(FixedEventTypeEvent):
    """Agent returns discovered models to the TUI."""
    event_type: EventType = EventType.MODEL_LIST_RESPONSE
    models: list[ModelEntry] = Field(default_factory=list)
    current_provider: str = ""
    current_model: str = ""
```

Where `ModelEntry` is a new Pydantic model in `breqy/domain/models.py`:

```python
class ModelEntry(BaseModel):
    """A model available from a provider, for model selector UI."""
    provider: str          # e.g. "copilot"
    model_id: str          # e.g. "gpt-4o"
    display_name: str      # e.g. "GPT-4o"
    is_authenticated: bool # whether provider credentials exist
```

#### `ModelSwitchRequestedEvent`

Sent by TUI → engine → agent. Tells agent to switch provider/model.

```python
class ModelSwitchRequestedEvent(FixedEventTypeEvent):
    """TUI requests the agent switch to a different provider/model."""
    event_type: EventType = EventType.MODEL_SWITCH_REQUESTED
    provider_id: str
    model_id: str
```

### Data Flows

#### Flow 1: Display current model (on agent connect)

```
Agent starts → _build_provider() → knows provider_id + model_id
  → sends ModelInfoEvent(provider_id, model_id) to engine
  → engine broadcasts to all clients (TUI)
  → TUI EventDispatcher routes MODEL_INFO to ChatScreen handler
  → ChatScreen updates AgentStatusBar display:
    "[green]● breqy[/green] copilot / gpt-4o"
```

**Agent side** (`runtime.py`): After sending `AgentLifecycleEvent(AGENT_CONNECTED)` in `run()`, also send `ModelInfoEvent` with `self._provider.provider_id` and `self._provider.model_id`.

**`_NullProvider` handling**: If `_build_provider()` fell back to `_NullProvider` (provider_id="null", model_id="null"), the agent still sends `ModelInfoEvent`. The TUI displays `"null / null"` in dim/warning style so the user knows something went wrong.

**Engine side** (`server.py`): `ModelInfoEvent` hits the default handler — publishes to bus, broadcasts to all clients except sender. No special routing needed.

**TUI side** (`app.py`): Register `EventDispatcher` handler for `MODEL_INFO`. In the handler, call `ChatScreen.update_model_info(provider_id, model_id)`.

**AgentStatusBar enhancement**: Add `self._model_info: tuple[str, str] | None = None` state. Add `update_model_info(provider_id: str, model_id: str)` method that stores the model info and calls `_refresh_display()`. Update `_refresh_display()` to append model info after the agent connection line. Display format: `"[green]● breqy[/green]  [cyan]copilot / gpt-4o[/cyan]"`. On `AGENT_DISCONNECTED`, clear `self._model_info` and re-render (model info shown as dim/cleared alongside the disconnected agent).

#### Flow 2: Open model selector (`ctrl+m`)

```
User presses ctrl+m → BreqyApp sends ModelListRequestedEvent to engine
  → engine forwards to agent (via send_to on primary agent)
  → agent calls list_models() on each available provider
  → agent sends ModelListResponseEvent(models=[...]) to engine
  → engine broadcasts to TUI
  → TUI receives response → populates ModelSelectScreen → pushes screen
```

**TUI side** (`app.py`): On `ctrl+m` binding, instead of immediately pushing `ModelSelectScreen`:
1. Find `session_id` by walking `screen_stack` to find the active `ChatScreen` (same pattern as `on_message_submitted()` at `app.py:351-356`). If no `ChatScreen` found, no-op.
2. If `self._model_list_pending` is `True`, ignore the request (debounce guard).
3. Set `self._model_list_pending = True`.
4. Send `ModelListRequestedEvent(session_id=session_id)` to engine.
5. When `MODEL_LIST_RESPONSE` arrives: set `self._model_list_pending = False`. Check that current screen is still a `ChatScreen`. Convert `ModelEntry` objects to `ModelOption` objects (mapping: `ModelOption(provider=e.provider, model_id=e.model_id, display_name=e.display_name)`). Push `ModelSelectScreen(models=options, current_model=response.current_model)`.

**Engine side** (`server.py`): `ModelListRequestedEvent` needs targeted routing to the session's primary agent. Add a handler case in `_handle_envelope()`: look up `session.primary_agent_id` from `SessionManager`, find agent's `client_id` from `AgentRegistry`, forward via `send_to()`. Same pattern as `_handle_user_message()`.

**Agent side** (`runtime.py`): Handle `ModelListRequestedEvent` in the `run()` listen loop. Call `_discover_models()` (see Flow 4 below). Wrap in `asyncio.to_thread()` since model discovery may involve synchronous HTTP. Send `ModelListResponseEvent` back to engine.

#### Flow 3: Switch model (user selects)

```
User selects model in ModelSelectScreen
  → ModelSelectScreen posts ModelSelected(provider, model_id)
  → BreqyApp.on_model_select_screen_model_selected() handler
  → sends ModelSwitchRequestedEvent(provider_id, model_id) to engine
  → engine forwards to agent
  → agent: naturally processes after current work completes (serial listen loop)
  → agent rebuilds provider → sends ModelInfoEvent(new_provider, new_model)
  → TUI updates AgentStatusBar
```

**No explicit busy guard needed**: The agent's `run()` method is an `async for envelope in self._client.listen()` loop that `await`s `handle_work()` synchronously. While `handle_work()` is running (blocking on `provider.stream()` which is a synchronous iterator), the listen loop is suspended. A `ModelSwitchRequestedEvent` sent during streaming will naturally be queued in the socket buffer and processed after `handle_work()` returns. The serial nature of the event loop provides the guard for free.

**Same-model guard**: If `event.provider_id == self._provider.provider_id and event.model_id == self._provider.model_id`, skip the rebuild and send `ModelInfoEvent` confirming the current model (idempotent).

**Provider rebuild**: `_build_provider()` is already a stateless module-level function. The agent calls it with a modified config:
```python
new_config = self._config.model_copy(update={"provider": event.provider_id, "model": event.model_id})
self._provider = _build_provider(new_config)
```

**Switch failure handling**: If `_build_provider()` returns a `_NullProvider` (provider string invalid, auth failure, etc.), the agent sends `ModelInfoEvent(provider_id="null", model_id="null")`. The TUI detects this and shows an error-style indicator. Additionally, the agent sends a `MessageSentEvent(role=SYSTEM, content="Failed to switch to {provider}/{model}: {reason}")` so the user sees the error in the chat. The old provider is preserved (the assignment only happens on success).

**Auth on demand**: If the new provider requires auth and credentials aren't cached, the provider's `stream()` method will trigger the auth flow on first use. This is handled by the existing notice event pattern — auth instructions appear as system messages in the TUI. The switch itself succeeds immediately (provider object is created); auth happens on first `stream()` call.

#### Flow 4: Dynamic model discovery

##### `list_models()` on `ModelProvider` ABC

Add to `breqy/agents/providers/base.py` as a **concrete method with default implementation** (not abstract — existing providers should work without overriding):

```python
class ModelProvider(ABC):
    # ... existing abstract methods ...

    def list_models(self) -> list[tuple[str, str]]:
        """Return available models as (model_id, display_name) pairs.

        Default returns just the configured model. Providers with
        API-based discovery override this.
        """
        return [(self.model_id, self.model_id)]
```

This is intentionally non-abstract. All existing `ModelProvider` methods are `@abstractmethod`, but `list_models()` is optional — providers work fine without it. Python ABCs fully support mixing abstract and concrete methods.

##### `CopilotProvider.list_models()` override

Query `GET https://api.githubcopilot.com/models`:

```python
def list_models(self) -> list[tuple[str, str]]:
    """Query Copilot API for available models."""
    token = self._authenticator.get_token()
    if token is None:
        return [(self.model_id, self.model_id)]  # fallback if not authed
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = httpx.get(
        "https://api.githubcopilot.com/models",
        headers=headers,
        timeout=10.0,
    )
    if resp.status_code != 200:
        return [(self.model_id, self.model_id)]
    data = resp.json()
    return [
        (m["id"], m.get("name", m["id"]))
        for m in data.get("data", [])
    ]
```

**Note**: `self._authenticator` (not `self._auth`) and `get_token()` (not `get_cached_token()`) match the actual attribute names in `CopilotProvider`.

##### Subprocess providers (claude, codex, gemini, qwen)

These use the default `list_models()` returning just their configured model. Dynamic discovery for these can be added later.

##### Agent-level discovery (`_discover_models`)

The agent-level function does NOT instantiate all providers. Instead:
- For the **currently active provider**: call `self._provider.list_models()` (may involve HTTP — wrap in `asyncio.to_thread()`)
- For **other providers**: return hardcoded fallback lists (known common models per provider)
- Set `is_authenticated` based on whether the `CredentialStore` has a token for that provider. Pass `CredentialStore` as a parameter to `AgentRuntime.__init__()` (currently created inside `_build_provider()` — extract it to be built in `main()` and passed to both `_build_provider()` and `AgentRuntime`).

Hardcoded fallback lists (in `breqy/agents/providers/adapters.py`):

```python
PROVIDER_FALLBACK_MODELS: dict[str, list[tuple[str, str]]] = {
    "copilot": [("gpt-4o", "GPT-4o"), ("gpt-4o-mini", "GPT-4o Mini"), ("o3-mini", "O3 Mini"), ("claude-3.5-sonnet", "Claude 3.5 Sonnet")],
    "claude": [("sonnet", "Claude Sonnet"), ("opus", "Claude Opus"), ("haiku", "Claude Haiku")],
    "codex": [("codex", "OpenAI Codex")],
    "gemini": [("gemini-2.0-flash", "Gemini 2.0 Flash"), ("gemini-2.5-pro", "Gemini 2.5 Pro")],
    "qwen": [("qwen-max", "Qwen Max"), ("qwen-plus", "Qwen Plus")],
}
```

For the active provider only, the dynamic `list_models()` result replaces the fallback.

**Async wrapping**: Since `list_models()` on `CopilotProvider` makes synchronous HTTP calls, `_discover_models()` must run the active provider's `list_models()` in a thread: `await asyncio.to_thread(self._provider.list_models)`.

## File Changes

### Domain layer

| File | Change |
|---|---|
| `breqy/domain/enums.py` | Add 4 `EventType` values |
| `breqy/domain/events.py` | Add `ModelInfoEvent`, `ModelListRequestedEvent`, `ModelListResponseEvent`, `ModelSwitchRequestedEvent` + register in `EVENT_TYPE_MAP` |
| `breqy/domain/models.py` | Add `ModelEntry` Pydantic model |

### Provider layer

| File | Change |
|---|---|
| `breqy/agents/providers/base.py` | Add `list_models()` concrete default method on `ModelProvider` |
| `breqy/agents/providers/copilot.py` | Override `list_models()` with API query |
| `breqy/agents/providers/adapters.py` | Add `PROVIDER_FALLBACK_MODELS` dict |

### Agent runtime

| File | Change |
|---|---|
| `breqy/agents/runtime.py` | Add `credential_store` param to `AgentRuntime.__init__()`. Extract `CredentialStore` creation to `main()`. Send `ModelInfoEvent` on connect. Handle `ModelListRequestedEvent` and `ModelSwitchRequestedEvent` in listen loop. Add `_discover_models()` method. Same-model guard. Switch failure handling with fallback to old provider. |

### Engine

| File | Change |
|---|---|
| `breqy/engine/server.py` | Route `ModelListRequestedEvent` and `ModelSwitchRequestedEvent` to session's primary agent (new handler case in `_handle_envelope()`). `ModelInfoEvent` and `ModelListResponseEvent` use default broadcast. |

### TUI

| File | Change |
|---|---|
| `breqy/tui/app.py` | Register `MODEL_INFO` and `MODEL_LIST_RESPONSE` handlers in `EventDispatcher`. Add `on_model_select_screen_model_selected()` handler. Change `ctrl+m` to send `ModelListRequestedEvent` with session_id. Add `_model_list_pending` debounce flag. Convert `ModelEntry` → `ModelOption` on response. Clear model info on `AGENT_DISCONNECTED`. |
| `breqy/tui/widgets/agent_status.py` | Add `self._model_info` state. Add `update_model_info()` and `clear_model_info()` methods. Update `_refresh_display()` to include model info. |
| `breqy/tui/screens/model_select.py` | No structural changes needed — `load_models()` and `ModelSelected` already work correctly. `ModelOption` dataclass remains unchanged; TUI converts `ModelEntry` → `ModelOption` before passing in. May add a loading state for while discovery is in flight. |

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Subprocess providers can't query models dynamically | Hardcoded fallback lists; `list_models()` default returns configured model |
| Auth flow blocks during device code polling | Already handled — notice events stream auth instructions before blocking |
| Switch during streaming | Serial event loop naturally queues switch until `handle_work()` completes — no explicit busy guard needed |
| Model discovery is slow (network call per provider) | Only active provider queries API; others use hardcoded fallbacks. Wrap in `asyncio.to_thread()`. |
| Race condition: TUI sends switch while agent processing list request | Both are handled in the same `run()` listen loop — sequential by design |
| Agent disconnects during model switch | TUI clears model info on `AGENT_DISCONNECTED` event |
| `ModelListResponseEvent` arrives after user navigates away | TUI handler checks current screen is `ChatScreen` before pushing `ModelSelectScreen` |
| Multiple rapid `ctrl+m` presses | `_model_list_pending` flag prevents duplicate requests |
| User selects current model | Same-model guard skips rebuild, sends confirming `ModelInfoEvent` |
| `_build_provider()` fails during switch | Old provider preserved; `MessageSentEvent(SYSTEM)` sent with error; `ModelInfoEvent` with old model sent |
| Sync HTTP in async context | `list_models()` wrapped in `asyncio.to_thread()` when called from async runtime |

## Test Strategy

- **Unit tests for new event classes**: serialization, validation, round-trip through envelope
- **Unit tests for `list_models()`**: default on base, override on copilot (mock HTTP)
- **Unit tests for `_discover_models()`**: mock providers, verify `ModelListResponseEvent` payload
- **Unit tests for `AgentRuntime` model switch**: verify provider rebuilt, `ModelInfoEvent` sent
- **Unit tests for `AgentRuntime` same-model guard**: verify no rebuild when same model selected
- **Unit tests for `AgentRuntime` switch failure**: verify old provider preserved, error sent
- **Unit tests for `AgentStatusBar.update_model_info()`**: verify display formatting
- **Unit tests for `AgentStatusBar.clear_model_info()`**: verify cleared on disconnect
- **Unit tests for `EventDispatcher` routing**: verify MODEL_INFO and MODEL_LIST_RESPONSE dispatched
- **Unit tests for engine routing**: verify `ModelListRequestedEvent` forwarded to correct agent
- **TUI tests for `ModelSelectScreen`**: verify `load_models()` with `ModelOption` data converted from `ModelEntry`
- **TUI tests for debounce**: verify `_model_list_pending` prevents duplicate requests

## Implementation Order

1. **Domain events & models** — new `EventType` values, event classes, `ModelEntry`
2. **Provider `list_models()`** — base default + copilot override
3. **Agent runtime** — Extract `CredentialStore` to `main()`, `ModelInfoEvent` on connect, `ModelListRequestedEvent` handler, `ModelSwitchRequestedEvent` handler, `_discover_models()`
4. **Engine routing** — forward model events to primary agent
5. **TUI wiring** — `AgentStatusBar` enhancement, `EventDispatcher` handlers, `ctrl+m` flow, `ModelSelected` handler, debounce, `ModelEntry` → `ModelOption` conversion
6. **Integration polish** — loading states, error handling, edge cases

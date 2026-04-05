# Thinking Indicator — Design Spec

**Date:** 2026-04-04  
**Status:** Superseded by reasoning-text-display (2026-04-05)  
**Feature:** Show a "Thinking..." indicator in the TUI chat view when a reasoning-capable model is processing, and display the actual reasoning summary text as a dim italic block.

---

## Background

GitHub Copilot's Responses API emits a `response.output_item.added` event with `item.type == "reasoning"` before the model begins streaming its answer.

**Initial probe findings** (2026-04-04): Responses-API models (gpt-5-mini, gpt-5.1, gpt-5.4, etc.) emitted `reasoning` output items with empty summaries (`summary: []`). No `response.reasoning_summary_text.delta` events were observed at that point.

**Updated findings** (2026-04-05): Requesting `reasoning: {"summary": "auto"}` in the API request body causes the API to stream the reasoning summary text via `response.reasoning_summary_text.delta` events. These are now captured and displayed. See the implementation in `breqy/agents/providers/copilot.py`.

- Chat-Completions-API models (all Claude models, older GPT): no reasoning events at all.

---

## Goal

Show a lightweight "Thinking..." status label in the chat view while the model's reasoning item is active, then replace it with the streamed reasoning summary as a dim italic block once reasoning completes.

---

## Scope

### In scope
- Provider layer: detect `reasoning` output items in `_do_stream_responses` and emit new provider events; stream `reasoning_summary_text.delta` as `reasoning_text` provider events.
- Domain layer: three new `EventType` values (`reasoning.started`, `reasoning.done`, `reasoning.text.chunk`) and three new event models.
- Runtime: dispatch the new events through the event bus.
- TUI: show and hide a "Thinking..." indicator in the chat view; buffer reasoning chunks and flush as dim italic block on `REASONING_DONE`.

### Out of scope
- Configuring the indicator appearance via env var or slash command (YAGNI).
- Extending the Chat Completions path (no reasoning events emitted there).

---

## Section 1 — Provider Layer

**File:** `breqy/agents/providers/base.py`

- Add `"reasoning_started"` and `"reasoning_done"` to the `ProviderEvent.kind` `Literal` type.

**File:** `breqy/agents/providers/copilot.py` — `_do_stream_responses` method

- When `response.output_item.added` is received and `event["item"]["type"] == "reasoning"`:
  - Yield `ProviderEvent(kind="reasoning_started")`.
- When `response.output_item.done` is received and `event["item"]["type"] == "reasoning"`:
  - Yield `ProviderEvent(kind="reasoning_done")`.
- No changes to `_do_stream` (Chat Completions path).

---

## Section 2 — Domain Events

**File:** `breqy/domain/enums.py`

Add to `EventType` enum:
```python
REASONING_STARTED = "reasoning_started"
REASONING_DONE = "reasoning_done"
```

**File:** `breqy/domain/events.py`

Add two new event models following the `MessageChunkEvent` pattern:

```python
class ReasoningStartedEvent(BaseModel):
    type: Literal[EventType.REASONING_STARTED] = EventType.REASONING_STARTED
    conversation_id: ConversationId
    agent_id: AgentId

class ReasoningDoneEvent(BaseModel):
    type: Literal[EventType.REASONING_DONE] = EventType.REASONING_DONE
    conversation_id: ConversationId
    agent_id: AgentId
```

---

## Section 3 — Runtime Dispatch

**File:** `breqy/agents/runtime.py` — provider event dispatch loop (~line 429–485)

Add two new branches alongside the existing `"chunk"` handler:

```python
elif provider_event.kind == "reasoning_started":
    await bus.publish(ReasoningStartedEvent(
        conversation_id=conversation_id,
        agent_id=agent_id,
    ))
elif provider_event.kind == "reasoning_done":
    await bus.publish(ReasoningDoneEvent(
        conversation_id=conversation_id,
        agent_id=agent_id,
    ))
```

---

## Section 4 — TUI

**File:** `breqy/tui/screens/chat.py`

- Register event handlers for `ReasoningStartedEvent` and `ReasoningDoneEvent`.
- On `ReasoningStartedEvent`: call `self.query_one(ChatView).show_thinking_indicator()`.
- On `ReasoningDoneEvent`: call `self.query_one(ChatView).hide_thinking_indicator()`.

**File:** `breqy/tui/widgets/chat_view.py`

Add two methods:

- `show_thinking_indicator()`:
  - If an indicator is already shown, no-op (idempotent).
  - Append a `Static("● Thinking...", id="thinking-indicator")` at the bottom of the message list (same mount point used for message bubbles).
  - Apply CSS class `thinking-indicator` (dimmed, italic).
- `hide_thinking_indicator()`:
  - Find the widget with `id="thinking-indicator"` and remove it if present.

**Safety net:** The existing `on_message_chunk` handler in `chat.py` is modified to call `hide_thinking_indicator()` on the first chunk received for a given turn (no new handler is added). This ensures the indicator is always removed even if `ReasoningDoneEvent` is missed.

**CSS (in the existing TUI stylesheet):**

```css
#thinking-indicator {
    color: $text-muted;
    text-style: italic;
    padding: 0 2;
}
```

---

## Testing

All changes are covered by unit tests following the project's Red-Green-Refactor TDD cycle:

| Layer | Test file | What is tested |
|---|---|---|
| Provider | `tests/unit/agents/providers/test_copilot.py` | `_do_stream_responses` yields `reasoning_started` / `reasoning_done` events for reasoning output items; non-reasoning items are unaffected |
| Domain | `tests/unit/domain/test_events.py` | New event models serialize/deserialize correctly |
| Runtime | `tests/unit/agents/test_runtime.py` | Dispatch loop publishes correct domain events for new provider event kinds |
| TUI | `tests/tui/test_chat_view.py` | `show_thinking_indicator` mounts widget; `hide_thinking_indicator` removes it; calling hide when none exists is a no-op |

---

## Files Changed

| File | Change |
|---|---|
| `breqy/agents/providers/base.py` | Add `reasoning_started`, `reasoning_done` to `ProviderEvent.kind` |
| `breqy/agents/providers/copilot.py` | Handle `reasoning` output items in `_do_stream_responses` |
| `breqy/domain/enums.py` | Add `REASONING_STARTED`, `REASONING_DONE` to `EventType` |
| `breqy/domain/events.py` | Add `ReasoningStartedEvent`, `ReasoningDoneEvent` |
| `breqy/agents/runtime.py` | Add dispatch branches for new event kinds |
| `breqy/tui/screens/chat.py` | Handle `ReasoningStartedEvent` / `ReasoningDoneEvent` |
| `breqy/tui/widgets/chat_view.py` | Add `show_thinking_indicator` / `hide_thinking_indicator` |
| `breqy/tui/app.tcss` (or equivalent) | Add `#thinking-indicator` CSS rule |

No new files are needed.

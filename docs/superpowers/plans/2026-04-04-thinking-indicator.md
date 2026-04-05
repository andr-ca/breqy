# Thinking Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a "Thinking..." label in the TUI chat view while a reasoning-capable model is processing, and remove it once text streaming begins.

**Architecture:** Four-layer change following the existing event bus pipeline: Provider → Domain → Runtime → TUI. The provider detects the `reasoning` output item from the Copilot Responses API and emits new `ProviderEvent` kinds; the runtime translates those into domain events; the TUI chat screen receives the domain events and shows/hides a `Static` widget in `ChatView`.

**Tech Stack:** Python 3.12, Pydantic v2, Textual, pytest, pytest-asyncio. All tests run with `pytest`.

---

## File Map

| File | Change |
|---|---|
| `breqy/agents/providers/base.py:44` | Add `"reasoning_started"` and `"reasoning_done"` to `ProviderEvent.kind` |
| `breqy/agents/providers/copilot.py:444-455` | Handle `reasoning` output items in `_do_stream_responses` |
| `breqy/domain/enums.py:58` | Add `REASONING_STARTED` and `REASONING_DONE` to `EventType` |
| `breqy/domain/events.py:505` | Add `ReasoningStartedEvent`, `ReasoningDoneEvent`, register in `EVENT_TYPE_MAP` |
| `breqy/agents/runtime.py:458` | Add dispatch branches for new provider event kinds |
| `breqy/tui/app.py:122-184` | Register routing for `REASONING_STARTED` / `REASONING_DONE` |
| `breqy/tui/screens/chat.py:146-153` | Add `handle_reasoning_started` / `handle_reasoning_done`; modify `handle_message_chunk` |
| `breqy/tui/widgets/chat_view.py` | Add `show_thinking_indicator` / `hide_thinking_indicator` |

No new files are needed.

---

## Task 1: Extend `ProviderEvent.kind` with reasoning variants

**Files:**
- Modify: `breqy/agents/providers/base.py:44`
- Test: `tests/unit/agents/providers/test_copilot.py`

- [ ] **Step 1: Write the failing test**

  In `tests/unit/agents/providers/test_copilot.py`, add at the bottom:

  ```python
  class TestProviderEventKind:
      def test_reasoning_started_kind_is_valid(self) -> None:
          from breqy.agents.providers.base import ProviderEvent

          e = ProviderEvent(kind="reasoning_started")
          assert e.kind == "reasoning_started"

      def test_reasoning_done_kind_is_valid(self) -> None:
          from breqy.agents.providers.base import ProviderEvent

          e = ProviderEvent(kind="reasoning_done")
          assert e.kind == "reasoning_done"
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/unit/agents/providers/test_copilot.py::TestProviderEventKind -v
  ```

  Expected: FAIL — `ValidationError` because `"reasoning_started"` is not a valid `Literal`.

- [ ] **Step 3: Extend `ProviderEvent.kind`**

  In `breqy/agents/providers/base.py`, change line 44 from:

  ```python
      kind: Literal["text", "tool_call", "complete", "notice"]
  ```

  to:

  ```python
      kind: Literal["text", "tool_call", "complete", "notice", "reasoning_started", "reasoning_done"]
  ```

- [ ] **Step 4: Run the tests to verify they pass**

  ```bash
  pytest tests/unit/agents/providers/test_copilot.py::TestProviderEventKind -v
  ```

  Expected: PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add breqy/agents/providers/base.py tests/unit/agents/providers/test_copilot.py
  git commit -m "feat(provider): add reasoning_started/done to ProviderEvent.kind"
  ```

---

## Task 2: Emit reasoning events in `_do_stream_responses`

**Files:**
- Modify: `breqy/agents/providers/copilot.py:444-455`
- Test: `tests/unit/agents/providers/test_copilot_responses.py`

- [ ] **Step 1: Write the failing tests**

  In `tests/unit/agents/providers/test_copilot_responses.py`, find the `TestStreamResponsesToolCall` class and add a new class after it:

  ```python
  class TestStreamResponsesReasoningItem:
      """_do_stream_responses emits reasoning_started / reasoning_done for reasoning output items."""

      def _make_provider(self) -> "CopilotProvider":
          from breqy.agents.providers.copilot import CopilotProvider
          from unittest.mock import MagicMock

          auth = MagicMock()
          auth.get_copilot_token.return_value = "tok"
          client = MagicMock()
          return CopilotProvider(model_id="gpt-5-mini", auth=auth, client=client)

      def _make_sse(self, *events) -> list[str]:
          import json
          lines = []
          for ev in events:
              lines.append(f"data: {json.dumps(ev)}")
              lines.append("")
          return lines

      def test_reasoning_output_item_emits_reasoning_started_then_done(self) -> None:
          from unittest.mock import MagicMock, patch
          from breqy.agents.providers.base import ProviderEvent, ProviderRequest
          from pathlib import Path

          reasoning_added = {
              "type": "response.output_item.added",
              "item": {"id": "r1", "type": "reasoning", "summary": []},
              "output_index": 0,
          }
          reasoning_done = {
              "type": "response.output_item.done",
              "item": {"id": "r1", "type": "reasoning", "summary": []},
              "output_index": 0,
          }
          text_delta = {"type": "response.output_text.delta", "delta": "Hello"}
          completed = {"type": "response.completed", "response": {"status": "completed"}}

          lines = self._make_sse(reasoning_added, reasoning_done, text_delta, completed, "[DONE]")
          mock_resp = MagicMock()
          mock_resp.status_code = 200
          mock_resp.iter_lines.return_value = iter(lines)
          mock_resp.__enter__ = MagicMock(return_value=mock_resp)
          mock_resp.__exit__ = MagicMock(return_value=False)

          provider = self._make_provider()
          provider._client.stream_responses.return_value = iter([
              reasoning_added, reasoning_done, text_delta, completed,
          ])

          request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
          events = list(provider._do_stream_responses("tok", request))

          kinds = [e.kind for e in events]
          assert "reasoning_started" in kinds
          assert "reasoning_done" in kinds
          # reasoning_started must come before reasoning_done
          assert kinds.index("reasoning_started") < kinds.index("reasoning_done")

      def test_non_reasoning_output_item_does_not_emit_reasoning_events(self) -> None:
          from breqy.agents.providers.base import ProviderRequest
          from pathlib import Path

          function_call_done = {
              "type": "response.output_item.done",
              "item": {
                  "type": "function_call",
                  "call_id": "c1",
                  "name": "read_file",
                  "arguments": '{"path": "/tmp/x"}',
              },
          }
          completed = {"type": "response.completed", "response": {"status": "completed"}}

          provider = self._make_provider()
          provider._client.stream_responses.return_value = iter([
              function_call_done, completed,
          ])

          request = ProviderRequest(prompt="hi", work_dir=Path("/tmp"))
          events = list(provider._do_stream_responses("tok", request))

          kinds = [e.kind for e in events]
          assert "reasoning_started" not in kinds
          assert "reasoning_done" not in kinds
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/unit/agents/providers/test_copilot_responses.py::TestStreamResponsesReasoningItem -v
  ```

  Expected: FAIL — `reasoning_started` / `reasoning_done` not in the emitted event kinds.

- [ ] **Step 3: Implement in `_do_stream_responses`**

  In `breqy/agents/providers/copilot.py`, inside `_do_stream_responses`, locate the `elif event_type == "response.output_item.done":` block (around line 445) and add handling for `response.output_item.added` before it:

  ```python
              # Reasoning item started
              elif event_type == "response.output_item.added":
                  item = event.get("item", {})
                  if item.get("type") == "reasoning":
                      yield ProviderEvent(kind="reasoning_started")

              # Tool call OR reasoning item done
              elif event_type == "response.output_item.done":
                  item = event.get("item", {})
                  if item.get("type") == "function_call":
                      yield ProviderEvent(
                          kind="tool_call",
                          tool_call=ToolCallDelta(
                              call_id=item.get("call_id", ""),
                              tool_name=item.get("name", ""),
                              arguments_chunk=item.get("arguments", ""),
                          ),
                      )
                  elif item.get("type") == "reasoning":
                      yield ProviderEvent(kind="reasoning_done")
  ```

  This replaces the existing `elif event_type == "response.output_item.done":` block — add the new `response.output_item.added` branch before it, and extend the `done` branch with the `elif item.get("type") == "reasoning"` clause.

- [ ] **Step 4: Run the tests to verify they pass**

  ```bash
  pytest tests/unit/agents/providers/test_copilot_responses.py::TestStreamResponsesReasoningItem -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full providers test suite to check for regressions**

  ```bash
  pytest tests/unit/agents/providers/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add breqy/agents/providers/copilot.py tests/unit/agents/providers/test_copilot_responses.py
  git commit -m "feat(provider): emit reasoning_started/done events from Responses API stream"
  ```

---

## Task 3: Add `REASONING_STARTED` / `REASONING_DONE` to domain

**Files:**
- Modify: `breqy/domain/enums.py:58`
- Modify: `breqy/domain/events.py:505`
- Test: `tests/unit/domain/test_events.py`

- [ ] **Step 1: Write the failing tests**

  In `tests/unit/domain/test_events.py`, add at the bottom:

  ```python
  class TestReasoningEvents:
      def test_reasoning_started_event_has_correct_type(self) -> None:
          from breqy.domain.events import ReasoningStartedEvent
          from breqy.domain.enums import EventType

          e = ReasoningStartedEvent(session_id="ses_1", agent_id="ag_1")
          assert e.event_type == EventType.REASONING_STARTED

      def test_reasoning_done_event_has_correct_type(self) -> None:
          from breqy.domain.events import ReasoningDoneEvent
          from breqy.domain.enums import EventType

          e = ReasoningDoneEvent(session_id="ses_1", agent_id="ag_1")
          assert e.event_type == EventType.REASONING_DONE

      def test_reasoning_started_rejects_wrong_event_type(self) -> None:
          from pydantic import ValidationError
          from breqy.domain.events import ReasoningStartedEvent
          from breqy.domain.enums import EventType

          with pytest.raises(ValidationError):
              ReasoningStartedEvent(
                  session_id="ses_1",
                  event_type=EventType.MESSAGE_CHUNK,
              )

      def test_reasoning_events_registered_in_deserializer(self) -> None:
          from breqy.domain.events import deserialize_event, ReasoningStartedEvent, ReasoningDoneEvent
          from breqy.domain.enums import EventType

          started = deserialize_event({
              "event_type": "reasoning_started",
              "session_id": "ses_1",
          })
          assert isinstance(started, ReasoningStartedEvent)

          done = deserialize_event({
              "event_type": "reasoning_done",
              "session_id": "ses_1",
          })
          assert isinstance(done, ReasoningDoneEvent)
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/unit/domain/test_events.py::TestReasoningEvents -v
  ```

  Expected: FAIL — `ReasoningStartedEvent` does not exist.

- [ ] **Step 3: Add enum values**

  In `breqy/domain/enums.py`, after line 58 (`MODEL_SWITCH_REQUESTED = "model.switch.requested"`), add:

  ```python
      REASONING_STARTED = "reasoning.started"
      REASONING_DONE = "reasoning.done"
  ```

  **Note:** Use dot-delimited values (`reasoning.started`, `reasoning.done`) to match the established `EventType` convention (e.g. `message.sent`, `tool.invocation.started`). The `ProviderEvent.kind` strings (`"reasoning_started"`, `"reasoning_done"`) are a separate internal namespace in the provider layer and do not need to match.

- [ ] **Step 4: Add event models**

  In `breqy/domain/events.py`, after the `# Model events` section (after `ModelSwitchRequestedEvent`, before `# Registry + deserializer`), add:

  ```python
  # --------------------------------------------------------------------------- #
  # Reasoning events
  # --------------------------------------------------------------------------- #


  class ReasoningStartedEvent(FixedEventTypeEvent):
      """Agent's model has begun a reasoning/thinking phase."""

      event_type: EventType = EventType.REASONING_STARTED


  class ReasoningDoneEvent(FixedEventTypeEvent):
      """Agent's model has finished its reasoning/thinking phase."""

      event_type: EventType = EventType.REASONING_DONE
  ```

  Then in `EVENT_TYPE_MAP` (near the bottom of the file), add the two new entries:

  ```python
      EventType.REASONING_STARTED: ReasoningStartedEvent,
      EventType.REASONING_DONE: ReasoningDoneEvent,
  ```

- [ ] **Step 5: Run the tests to verify they pass**

  ```bash
  pytest tests/unit/domain/test_events.py::TestReasoningEvents -v
  ```

  Expected: PASS.

- [ ] **Step 6: Run the full domain test suite to check for regressions**

  ```bash
  pytest tests/unit/domain/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add breqy/domain/enums.py breqy/domain/events.py tests/unit/domain/test_events.py
  git commit -m "feat(domain): add ReasoningStartedEvent and ReasoningDoneEvent"
  ```

---

## Task 4: Dispatch reasoning events in the runtime

**Files:**
- Modify: `breqy/agents/runtime.py:458`
- Test: `tests/unit/agents/test_runtime.py`

- [ ] **Step 1: Write the failing tests**

  In `tests/unit/agents/test_runtime.py`, find an existing test that verifies `MessageChunkEvent` is sent for `ProviderEvent(kind="text")` and use the same fixture/helper pattern. Add a new test class at the bottom:

  ```python
  class TestRuntimeReasoningEventDispatch:
      """Runtime dispatches ReasoningStartedEvent / ReasoningDoneEvent for reasoning provider events."""

      @pytest.mark.asyncio
      async def test_reasoning_started_published_to_client(self, make_runtime) -> None:
          """reasoning_started provider event → ReasoningStartedEvent sent to client."""
          from breqy.agents.providers.base import ProviderEvent
          from breqy.domain.events import ReasoningStartedEvent
          from breqy.domain.enums import EventType

          runtime = make_runtime(provider_events=[
              ProviderEvent(kind="reasoning_started"),
              ProviderEvent(kind="text", text="Hello"),
              _complete_event(),
          ])
          await runtime.handle_work_requested(_sample_work_event())

          sent_types = [e.event_type for e in runtime._client.sent_events]
          assert EventType.REASONING_STARTED in sent_types

      @pytest.mark.asyncio
      async def test_reasoning_done_published_to_client(self, make_runtime) -> None:
          """reasoning_done provider event → ReasoningDoneEvent sent to client."""
          from breqy.agents.providers.base import ProviderEvent
          from breqy.domain.enums import EventType

          runtime = make_runtime(provider_events=[
              ProviderEvent(kind="reasoning_started"),
              ProviderEvent(kind="reasoning_done"),
              ProviderEvent(kind="text", text="Hello"),
              _complete_event(),
          ])
          await runtime.handle_work_requested(_sample_work_event())

          sent_types = [e.event_type for e in runtime._client.sent_events]
          assert EventType.REASONING_DONE in sent_types

      @pytest.mark.asyncio
      async def test_reasoning_started_before_reasoning_done(self, make_runtime) -> None:
          """reasoning_started is dispatched before reasoning_done."""
          from breqy.agents.providers.base import ProviderEvent
          from breqy.domain.enums import EventType

          runtime = make_runtime(provider_events=[
              ProviderEvent(kind="reasoning_started"),
              ProviderEvent(kind="reasoning_done"),
              ProviderEvent(kind="text", text="Hi"),
              _complete_event(),
          ])
          await runtime.handle_work_requested(_sample_work_event())

          sent_types = [e.event_type for e in runtime._client.sent_events]
          started_idx = sent_types.index(EventType.REASONING_STARTED)
          done_idx = sent_types.index(EventType.REASONING_DONE)
          assert started_idx < done_idx
  ```

  Note: `make_runtime`, `_complete_event`, and `_sample_work_event` are helpers already defined in the file. Check the file for the exact fixture names (search for `def make_runtime` or `@pytest.fixture`).

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/unit/agents/test_runtime.py::TestRuntimeReasoningEventDispatch -v
  ```

  Expected: FAIL — `REASONING_STARTED` not in sent event types.

- [ ] **Step 3: Add dispatch branches in `runtime.py`**

  In `breqy/agents/runtime.py`, first add the imports at the top of the file (find the existing `ReasoningStartedEvent` / `ReasoningDoneEvent` import block, or add after `MessageChunkEvent`):

  ```python
  from breqy.domain.events import (
      ...
      ReasoningDoneEvent,
      ReasoningStartedEvent,
      ...
  )
  ```

  Then in the provider event dispatch loop (around line 458), after the `if provider_event.kind == "notice"` block and before `if provider_event.kind == "text"`, add:

  ```python
                      if provider_event.kind == "reasoning_started":
                          await self._client.send_event(
                              ReasoningStartedEvent(
                                  session_id=event.session_id,
                                  agent_id=event.agent_id,
                                  correlation_id=event.correlation_id,
                              )
                          )
                          continue

                      if provider_event.kind == "reasoning_done":
                          await self._client.send_event(
                              ReasoningDoneEvent(
                                  session_id=event.session_id,
                                  agent_id=event.agent_id,
                                  correlation_id=event.correlation_id,
                              )
                          )
                          continue
  ```

- [ ] **Step 4: Run the tests to verify they pass**

  ```bash
  pytest tests/unit/agents/test_runtime.py::TestRuntimeReasoningEventDispatch -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full runtime test suite to check for regressions**

  ```bash
  pytest tests/unit/agents/test_runtime.py -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add breqy/agents/runtime.py tests/unit/agents/test_runtime.py
  git commit -m "feat(runtime): dispatch ReasoningStartedEvent/ReasoningDoneEvent from provider events"
  ```

---

## Task 5: Wire routing in the TUI app

**Files:**
- Modify: `breqy/tui/app.py:122-184`
- Test: `tests/tui/test_app.py` (existing file — add new test class)

- [ ] **Step 1: Write the failing test**

  In `tests/tui/test_app.py`, find the `TestDispatcherSetup` class (around line 145). It tests handler registration using `app._dispatcher.has_handler(EventType.X)` — follow that exact pattern. Add these two tests to that class:

  ```python
      def test_dispatcher_has_handler_for_reasoning_started(self) -> None:
          from breqy.domain.enums import EventType

          app = BreqyApp()
          assert app._dispatcher.has_handler(EventType.REASONING_STARTED)

      def test_dispatcher_has_handler_for_reasoning_done(self) -> None:
          from breqy.domain.enums import EventType

          app = BreqyApp()
          assert app._dispatcher.has_handler(EventType.REASONING_DONE)
  ```

- [ ] **Step 2: Run the test to verify it fails**

  ```bash
  pytest tests/tui/test_app.py::TestDispatcherSetup::test_dispatcher_has_handler_for_reasoning_started tests/tui/test_app.py::TestDispatcherSetup::test_dispatcher_has_handler_for_reasoning_done -v
  ```

  Expected: FAIL — `has_handler` returns `False` because the subscriptions are not yet registered.

- [ ] **Step 3: Add routing entries**

  In `breqy/tui/app.py`, in the event subscription block (the section that starts with `EventType.MESSAGE_SENT`), add two new subscriptions after the existing `MESSAGE_CHUNK` subscription:

  ```python
          self._bus.subscribe(
              EventType.REASONING_STARTED,
              lambda e: self._route_to_chat("handle_reasoning_started", e),
          )
          self._bus.subscribe(
              EventType.REASONING_DONE,
              lambda e: self._route_to_chat("handle_reasoning_done", e),
          )
  ```

  No import change is needed — `EventType` is already imported.

- [ ] **Step 4: Run the test to verify it passes**

  ```bash
  pytest tests/tui/test_app.py::TestDispatcherSetup::test_dispatcher_has_handler_for_reasoning_started tests/tui/test_app.py::TestDispatcherSetup::test_dispatcher_has_handler_for_reasoning_done -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full TUI test suite to check for regressions**

  ```bash
  pytest tests/tui/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add breqy/tui/app.py tests/tui/test_app.py
  git commit -m "feat(tui): route REASONING_STARTED/DONE events to chat screen"
  ```

## Task 6: `ChatView` — show/hide thinking indicator

**Files:**
- Modify: `breqy/tui/widgets/chat_view.py`
- Test: `tests/tui/test_chat_view.py`

- [ ] **Step 1: Write the failing tests**

  In `tests/tui/test_chat_view.py`, add at the bottom:

  ```python
  class TestThinkingIndicator:
      """ChatView.show_thinking_indicator / hide_thinking_indicator."""

      @pytest.mark.asyncio
      async def test_show_thinking_indicator_mounts_widget(self) -> None:
          from textual.widgets import Static

          app = ChatViewApp()
          async with app.run_test() as pilot:
              chat = app.query_one(ChatView)
              chat.show_thinking_indicator()
              await pilot.pause()
              indicators = app.query("#thinking-indicator")
              assert len(indicators) == 1

      @pytest.mark.asyncio
      async def test_show_thinking_indicator_is_idempotent(self) -> None:
          app = ChatViewApp()
          async with app.run_test() as pilot:
              chat = app.query_one(ChatView)
              chat.show_thinking_indicator()
              chat.show_thinking_indicator()
              await pilot.pause()
              indicators = app.query("#thinking-indicator")
              assert len(indicators) == 1

      @pytest.mark.asyncio
      async def test_hide_thinking_indicator_removes_widget(self) -> None:
          app = ChatViewApp()
          async with app.run_test() as pilot:
              chat = app.query_one(ChatView)
              chat.show_thinking_indicator()
              await pilot.pause()
              chat.hide_thinking_indicator()
              await pilot.pause()
              indicators = app.query("#thinking-indicator")
              assert len(indicators) == 0

      @pytest.mark.asyncio
      async def test_hide_thinking_indicator_is_noop_when_none_shown(self) -> None:
          """hide_thinking_indicator does not raise if no indicator is mounted."""
          app = ChatViewApp()
          async with app.run_test() as pilot:
              chat = app.query_one(ChatView)
              chat.hide_thinking_indicator()  # should not raise
              await pilot.pause()
              indicators = app.query("#thinking-indicator")
              assert len(indicators) == 0
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/tui/test_chat_view.py::TestThinkingIndicator -v
  ```

  Expected: FAIL — `AttributeError: ChatView has no method show_thinking_indicator`.

- [ ] **Step 3: Implement in `chat_view.py`**

  In `breqy/tui/widgets/chat_view.py`, add these two methods after `clear_messages`:

  ```python
      def show_thinking_indicator(self) -> None:
          """Show a 'Thinking...' indicator at the bottom of the chat.

          Idempotent — calling this multiple times only mounts one indicator.
          """
          if self.query("#thinking-indicator"):
              return
          from textual.widgets import Static
          self.mount(Static("● Thinking...", id="thinking-indicator", classes="thinking-indicator"))

      def hide_thinking_indicator(self) -> None:
          """Remove the 'Thinking...' indicator if it is present.

          No-op if no indicator is currently shown.
          """
          for widget in self.query("#thinking-indicator"):
              widget.remove()
  ```

  Also add the following CSS rule to `ChatView.DEFAULT_CSS`:

  ```css
      .thinking-indicator {
          color: $text-muted;
          text-style: italic;
          padding: 0 2;
      }
  ```

- [ ] **Step 4: Run the tests to verify they pass**

  ```bash
  pytest tests/tui/test_chat_view.py::TestThinkingIndicator -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full TUI test suite to check for regressions**

  ```bash
  pytest tests/tui/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add breqy/tui/widgets/chat_view.py tests/tui/test_chat_view.py
  git commit -m "feat(tui): add show/hide thinking indicator to ChatView"
  ```

---

## Task 7: `ChatScreen` — handle reasoning events and update safety net

**Files:**
- Modify: `breqy/tui/screens/chat.py`
- Test: `tests/tui/test_chat_screen.py` (existing file — add new test class)

- [ ] **Step 1: Write the failing tests**

  In `tests/tui/test_chat_screen.py`, add at the bottom. The file already defines `ChatScreenApp` (a minimal `App` that pushes a `ChatScreen`) and `_get_screen(app)` (returns the active `ChatScreen`). Use those helpers directly:

  ```python
  class TestChatScreenReasoningHandlers:
      """ChatScreen calls show/hide thinking indicator on reasoning events."""

      @pytest.mark.asyncio
      async def test_handle_reasoning_started_shows_indicator(self) -> None:
          from breqy.domain.events import ReasoningStartedEvent

          event = ReasoningStartedEvent(session_id=SESSION_ID, agent_id="ag_1")

          app = ChatScreenApp()
          async with app.run_test() as pilot:
              screen = _get_screen(app)
              screen.handle_reasoning_started(event)
              await pilot.pause()
              assert len(app.query("#thinking-indicator")) == 1

      @pytest.mark.asyncio
      async def test_handle_reasoning_done_hides_indicator(self) -> None:
          from breqy.domain.events import ReasoningStartedEvent, ReasoningDoneEvent

          app = ChatScreenApp()
          async with app.run_test() as pilot:
              screen = _get_screen(app)
              screen.handle_reasoning_started(ReasoningStartedEvent(session_id=SESSION_ID, agent_id="ag_1"))
              await pilot.pause()
              screen.handle_reasoning_done(ReasoningDoneEvent(session_id=SESSION_ID, agent_id="ag_1"))
              await pilot.pause()
              assert len(app.query("#thinking-indicator")) == 0

      @pytest.mark.asyncio
      async def test_handle_message_chunk_hides_indicator(self) -> None:
          """First MessageChunkEvent also removes the thinking indicator (safety net)."""
          from breqy.domain.events import ReasoningStartedEvent, MessageChunkEvent

          app = ChatScreenApp()
          async with app.run_test() as pilot:
              screen = _get_screen(app)
              screen.handle_reasoning_started(ReasoningStartedEvent(session_id=SESSION_ID, agent_id="ag_1"))
              await pilot.pause()
              screen.handle_message_chunk(MessageChunkEvent(
                  session_id=SESSION_ID,
                  agent_id="ag_1",
                  message_id="msg_1",
                  chunk="Hello",
                  chunk_index=0,
              ))
              await pilot.pause()
              assert len(app.query("#thinking-indicator")) == 0
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  ```bash
  pytest tests/tui/test_chat_screen.py::TestChatScreenReasoningHandlers -v
  ```

  Expected: FAIL — `handle_reasoning_started` does not exist on `ChatScreen`.

- [ ] **Step 3: Implement in `chat.py`**

  First, update imports at the top of `breqy/tui/screens/chat.py`:

  ```python
  from breqy.domain.events import (
      AgentLifecycleEvent,
      ApprovalRequestedEvent,
      MessageChunkEvent,
      MessageSentEvent,
      ModelInfoEvent,
      ReasoningDoneEvent,
      ReasoningStartedEvent,
      TaskUpdatedEvent,
      ToolInvocationCompletedEvent,
      ToolInvocationFailedEvent,
      ToolInvocationStartedEvent,
      ToolOutputChunkEvent,
  )
  ```

  Then modify `handle_message_chunk` to call `hide_thinking_indicator()` first:

  ```python
      def handle_message_chunk(self, event: MessageChunkEvent) -> None:
          """Route a ``MessageChunkEvent`` to the ``ChatView`` for streaming.

          Also hides the thinking indicator if it is still showing (safety net).
          """
          chat_view = self.query_one(ChatView)
          chat_view.hide_thinking_indicator()
          chat_view.add_chunk(
              message_id=event.message_id,
              chunk=event.chunk,
              chunk_index=event.chunk_index,
          )
  ```

  Then add two new handlers after `handle_message_chunk`:

  ```python
      def handle_reasoning_started(self, event: ReasoningStartedEvent) -> None:
          """Show the 'Thinking...' indicator when the model enters a reasoning phase."""
          self.query_one(ChatView).show_thinking_indicator()

      def handle_reasoning_done(self, event: ReasoningDoneEvent) -> None:
          """Remove the 'Thinking...' indicator when the reasoning phase ends."""
          self.query_one(ChatView).hide_thinking_indicator()
  ```

- [ ] **Step 4: Run the tests to verify they pass**

  ```bash
  pytest tests/tui/test_chat_screen.py::TestChatScreenReasoningHandlers -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run the full TUI test suite to check for regressions**

  ```bash
  pytest tests/tui/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add breqy/tui/screens/chat.py tests/tui/test_chat_screen.py
  git commit -m "feat(tui): handle reasoning events in ChatScreen, update safety net in message_chunk"
  ```

---

## Task 8: Full test suite and coverage check

- [ ] **Step 1: Run the complete test suite**

  ```bash
  pytest tests/ -v
  ```

  Expected: all tests pass.

- [ ] **Step 2: Check coverage**

  ```bash
  pytest tests/ --cov=breqy --cov-report=term-missing
  ```

  Check that the new code paths in `base.py`, `copilot.py`, `enums.py`, `events.py`, `runtime.py`, `chat.py`, and `chat_view.py` are covered. Refer to `agents/core.instructions.md` for the project's coverage threshold.

- [ ] **Step 3: Commit if any coverage gaps prompted extra tests**

  If you added tests to close gaps:

  ```bash
  git add -A
  git commit -m "test: close coverage gaps for thinking indicator feature"
  ```

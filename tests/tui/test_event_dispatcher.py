"""Tests for breqy.tui.events — EventDispatcher."""
from __future__ import annotations

import pytest

from breqy.domain.enums import EventType
from breqy.domain.events import (
    Event,
    MessageChunkEvent,
    MessageSentEvent,
    SessionCreatedEvent,
)
from breqy.tui.events import EventDispatcher


class TestEventDispatcherInit:
    """Test EventDispatcher initialization."""

    def test_creates_empty_dispatcher(self) -> None:
        dispatcher = EventDispatcher()
        assert not dispatcher.has_handler(EventType.MESSAGE_SENT)


class TestEventDispatcherRegister:
    """Test handler registration."""

    def test_registers_handler(self) -> None:
        dispatcher = EventDispatcher()
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: None)
        assert dispatcher.has_handler(EventType.MESSAGE_SENT)

    def test_registers_multiple_handlers_for_same_type(self) -> None:
        dispatcher = EventDispatcher()
        calls: list[str] = []
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: calls.append("first"))
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: calls.append("second"))
        assert dispatcher.has_handler(EventType.MESSAGE_SENT)

    def test_has_handler_returns_false_for_unregistered_type(self) -> None:
        dispatcher = EventDispatcher()
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: None)
        assert not dispatcher.has_handler(EventType.SESSION_CREATED)


class TestEventDispatcherDispatch:
    """Test event dispatching."""

    def test_dispatches_to_registered_handler(self) -> None:
        dispatcher = EventDispatcher()
        received: list[Event] = []
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: received.append(e))

        event = MessageSentEvent(
            session_id="ses_1",
            message_id="msg_1",
            role="user",
            content="hello",
        )
        dispatcher.dispatch(event)
        assert len(received) == 1
        assert received[0] is event

    def test_dispatches_to_multiple_handlers_in_order(self) -> None:
        dispatcher = EventDispatcher()
        calls: list[str] = []
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: calls.append("first"))
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: calls.append("second"))

        event = MessageSentEvent(
            session_id="ses_1",
            message_id="msg_1",
            role="user",
            content="hello",
        )
        dispatcher.dispatch(event)
        assert calls == ["first", "second"]

    def test_dispatch_with_no_handlers_does_nothing(self) -> None:
        dispatcher = EventDispatcher()
        event = SessionCreatedEvent(session_id="ses_1")
        # Should not raise
        dispatcher.dispatch(event)

    def test_dispatch_only_triggers_matching_type(self) -> None:
        dispatcher = EventDispatcher()
        sent_calls: list[Event] = []
        chunk_calls: list[Event] = []
        dispatcher.register(EventType.MESSAGE_SENT, lambda e: sent_calls.append(e))
        dispatcher.register(EventType.MESSAGE_CHUNK, lambda e: chunk_calls.append(e))

        event = MessageSentEvent(
            session_id="ses_1",
            message_id="msg_1",
            role="user",
            content="hello",
        )
        dispatcher.dispatch(event)
        assert len(sent_calls) == 1
        assert len(chunk_calls) == 0

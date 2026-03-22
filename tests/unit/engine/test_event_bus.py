"""Tests for in-process async event bus."""
from __future__ import annotations

import pytest

from breqy.engine.event_bus import EventBus
from breqy.domain.events import MessageSentEvent, ToolInvocationStartedEvent
from breqy.domain.enums import EventType


@pytest.mark.asyncio
async def test_subscribe_and_receive():
    """subscribe() handler receives a matching published event."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.MESSAGE_SENT, handler)

    event = MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    )
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].event_type == EventType.MESSAGE_SENT


@pytest.mark.asyncio
async def test_wildcard_subscribe():
    """subscribe_all() handler receives all event types."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe_all(handler)

    await bus.publish(MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    ))
    await bus.publish(ToolInvocationStartedEvent(
        session_id="ses_1", agent_id="breqy", invocation_id="inv_1",
        tool_name="shell", summary="ls"
    ))

    assert len(received) == 2


@pytest.mark.asyncio
async def test_unsubscribe():
    """unsubscribe() removes the handler — no events received after."""
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    sub_id = bus.subscribe(EventType.MESSAGE_SENT, handler)
    bus.unsubscribe(sub_id)

    await bus.publish(MessageSentEvent(
        session_id="ses_1", message_id="msg_1", role="user", content="Hi"
    ))

    assert len(received) == 0

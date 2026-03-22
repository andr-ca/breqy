"""In-process async event bus for the Breqy engine.

Supports typed subscriptions and wildcard (all-events) listeners.
Handlers are invoked inline (not as tasks) to keep ordering deterministic.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

import structlog

from breqy.domain.enums import EventType
from breqy.domain.events import Event
from breqy.domain.ids import generate_prefixed_id

logger = structlog.get_logger(__name__)

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish/subscribe event bus.

    Thread-safety: designed for single-thread asyncio use only.
    """

    def __init__(self) -> None:
        self._typed_handlers: dict[EventType, dict[str, EventHandler]] = {}
        self._wildcard_handlers: dict[str, EventHandler] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> str:
        """Subscribe to a specific event type. Returns subscription ID."""
        sub_id = generate_prefixed_id("sub")
        self._typed_handlers.setdefault(event_type, {})[sub_id] = handler
        return sub_id

    def subscribe_all(self, handler: EventHandler) -> str:
        """Subscribe to all event types. Returns subscription ID."""
        sub_id = generate_prefixed_id("sub")
        self._wildcard_handlers[sub_id] = handler
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscription by ID (typed or wildcard)."""
        self._wildcard_handlers.pop(sub_id, None)
        for handlers in self._typed_handlers.values():
            handlers.pop(sub_id, None)

    async def publish(self, event: Event) -> None:
        """Deliver event to all matching subscribers."""
        handlers: list[EventHandler] = list(
            self._typed_handlers.get(event.event_type, {}).values()
        )
        handlers.extend(self._wildcard_handlers.values())

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler raised",
                    event_type=str(event.event_type),
                )

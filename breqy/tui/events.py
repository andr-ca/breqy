"""Event dispatcher for mapping domain events to TUI handlers.

Pure logic — no Textual dependency.
"""
from __future__ import annotations

from collections.abc import Callable

from breqy.domain.enums import EventType
from breqy.domain.events import Event


class EventDispatcher:
    """Maps ``EventType`` values to lists of handler callbacks."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}

    def register(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Register a handler for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def dispatch(self, event: Event) -> None:
        """Dispatch an event to all registered handlers for its event_type."""
        for handler in self._handlers.get(event.event_type, []):
            handler(event)

    def has_handler(self, event_type: EventType) -> bool:
        """Return True if at least one handler is registered for *event_type*."""
        return bool(self._handlers.get(event_type))

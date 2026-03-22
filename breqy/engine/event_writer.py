"""Centralized sequential event writer (STR-05).

All events must flow through this writer. Agents must never write
directly to the database — all writes go through EventWriter.write().
This eliminates SQLite write contention by serialising all DB writes
through a single asyncio.Queue consumer.
"""

from __future__ import annotations

import asyncio

import structlog

from breqy.domain.events import Event
from breqy.storage.interfaces import EventRepository

logger = structlog.get_logger(__name__)


class EventWriter:
    """Accepts events from any async producer and writes them one-at-a-time.

    Usage::

        writer = EventWriter(event_repo)
        await writer.start()
        await writer.write(some_event)  # from any coroutine
        await writer.stop()             # flushes queue before returning
    """

    def __init__(self, event_repo: EventRepository) -> None:
        self._repo = event_repo
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background writer task."""
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Signal shutdown and wait for all queued events to be written."""
        # None sentinel tells the consumer to exit
        await self._queue.put(None)
        if self._task is not None:
            await self._task
            self._task = None

    async def write(self, event: Event) -> None:
        """Enqueue an event for sequential writing."""
        await self._queue.put(event)

    async def _run(self) -> None:
        """Consumer loop — processes events in insertion order."""
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            try:
                await self._repo.append(item)
            except Exception:
                logger.exception("EventWriter: failed to write event %s", item.event_id)
            finally:
                self._queue.task_done()

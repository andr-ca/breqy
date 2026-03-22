"""Agent/TUI-side A2A client.

Connects to the engine's Unix socket, sends events, and
listens for incoming events via async iteration.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter, connect_unix
from breqy.domain.events import Event

logger = logging.getLogger(__name__)


class A2AClient:
    """Client that connects to the engine's A2A server."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._frame_reader: FrameReader | None = None
        self._frame_writer: FrameWriter | None = None

    async def connect(self) -> None:
        """Establish connection to the engine socket."""
        self._reader, self._writer = await connect_unix(self._socket_path)
        self._frame_reader = FrameReader(self._reader)
        self._frame_writer = FrameWriter(self._writer)
        logger.info("Connected to engine at %s", self._socket_path)

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._frame_reader = None
        self._frame_writer = None

    async def send_envelope(self, envelope: Envelope) -> None:
        """Send a pre-built envelope."""
        if self._frame_writer is None:
            raise ConnectionError("Not connected")
        await self._frame_writer.write_envelope(envelope)

    async def send_event(self, event: Event) -> None:
        """Wrap event in envelope and send."""
        envelope = Envelope.from_event(event)
        await self.send_envelope(envelope)

    async def listen(self) -> AsyncIterator[Envelope]:
        """Async iterator that yields envelopes from the server."""
        if self._frame_reader is None:
            raise ConnectionError("Not connected")
        while True:
            try:
                envelope = await self._frame_reader.read_envelope()
                if envelope is None:
                    break
                yield envelope
            except asyncio.IncompleteReadError:
                break
            except Exception as exc:
                logger.error("Error reading from server: %s", exc)
                break
